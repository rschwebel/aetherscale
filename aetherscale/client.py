#!/usr/bin/env python

import argparse
import json
import pika
import pika.exceptions
import sys


class ServerCommunication:
    def __init__(self):
        self.queue = 'vm-queue'

    def __enter__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(host='localhost'))
        self.channel = self.connection.channel()

        self.channel.queue_declare(queue=self.queue)

        self.channel.basic_consume(
            queue='amq.rabbitmq.reply-to',
            on_message_callback=self.on_response,
            auto_ack=True)

        return self

    def on_response(self, ch, method, properties, body):
        self.responses.append(json.loads(body))

        # TODO: Stopping consuming on the first message only works
        # as long as we only expect one message
        self.channel.stop_consuming()

    def on_timeout(self):
        self.channel.stop_consuming()

    def send_msg(self, data, response_expected=False):
        self.responses = []

        reply_to = None
        if response_expected:
            reply_to = 'amq.rabbitmq.reply-to'

        self.channel.basic_publish(
            exchange='',
            routing_key=self.queue,
            properties=pika.BasicProperties(
                reply_to=reply_to,
                content_type='application/json',
            ),
            body=json.dumps(data).encode('utf-8'))

        if response_expected:
            self.connection.call_later(5, self.on_timeout)
            self.channel.start_consuming()

        return self.responses

    def __exit__(self, exc_type, exc_value, traceback):
        self.connection.close()


def main():
    parser = argparse.ArgumentParser(
        description='Manage aetherscale instances')
    subparsers = parser.add_subparsers(dest='subparser_name')

    create_vm_parser = subparsers.add_parser('create-vm')
    create_vm_parser.add_argument(
        '--image', help='Name of the image to create a VM from', required=True)
    start_vm_parser = subparsers.add_parser('start-vm')
    start_vm_parser.add_argument(
        '--vm-id', dest='vm_id', help='ID of the VM to start', required=True)
    stop_vm_parser = subparsers.add_parser('stop-vm')
    stop_vm_parser.add_argument(
        '--vm-id', dest='vm_id', help='ID of the VM to stop', required=True)
    delete_vm_parser = subparsers.add_parser('delete-vm')
    delete_vm_parser.add_argument(
        '--vm-id', dest='vm_id', help='ID of the VM to delete', required=True)
    subparsers.add_parser('list-vms')

    args = parser.parse_args()

    if args.subparser_name == 'list-vms':
        response_expected = True
        data = {
            'command': 'list-vms',
        }
    elif args.subparser_name == 'create-vm':
        response_expected = True
        data = {
            'command': 'create-vm',
            'options': {
                'image': args.image,
            }
        }
    elif args.subparser_name in ['start-vm', 'stop-vm', 'delete-vm']:
        response_expected = True
        data = {
            'command': args.subparser_name,
            'options': {
                'vm-id': args.vm_id,
            }
        }
    else:
        parser.print_usage()
        sys.exit(1)

    try:
        with ServerCommunication() as c:
            result = c.send_msg(data, response_expected)
            print(result)
    except pika.exceptions.AMQPConnectionError:
        print('Could not connect to AMQP broker. Is it running?',
              file=sys.stderr)
