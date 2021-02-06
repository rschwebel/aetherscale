import logging
import json
from pathlib import Path
import pika
from typing import Any, Callable, Dict, Iterator

from aetherscale import config
from aetherscale import services
from aetherscale.computing import ComputingHandler, RADVD_SERVICE_NAME
import aetherscale.vpn.radvd

EXCHANGE_NAME = 'computing'
COMPETING_QUEUE = 'computing-competing'
QUEUE_COMMANDS_MAP = {
    '': ['list-vms', 'start-vm', 'stop-vm', 'delete-vm'],
    COMPETING_QUEUE: ['create-vm'],
}


def noop_responder(_: Dict[str, Any]):
    pass


def create_rabbitmq_responder(ch, reply_to: str, correlation_id: str):
    def rabbitmq_responder(message: Dict[str, Any]):
        ch.basic_publish(
            exchange='',
            routing_key=reply_to,
            properties=pika.BasicProperties(
                correlation_id=correlation_id
            ),
            body=json.dumps(message))

    return rabbitmq_responder


def callback(ch, method, properties, body, handler: ComputingHandler):
    command_fn: Dict[str, Callable[[Dict[str, Any]], Iterator[Any]]] = {
        'list-vms': handler.list_vms,
        'create-vm': handler.create_vm,
        'start-vm': handler.start_vm,
        'stop-vm': handler.stop_vm,
        'delete-vm': handler.delete_vm,
    }

    message = body.decode('utf-8')
    logging.debug('Received message: ' + message)

    data = json.loads(message)

    try:
        command = data['command']
    except KeyError:
        logging.error('No "command" specified in message')
        return

    try:
        fn = command_fn[command]
    except KeyError:
        logging.error(f'Invalid command "{command}" specified')
        return

    if properties.reply_to:
        responder = create_rabbitmq_responder(
            ch, properties.reply_to, properties.correlation_id)
    else:
        responder = noop_responder

    options = data.get('options', {})
    try:
        for response in fn(options):
            # if a function wants to return a response
            # set its execution status to success
            resp_message = {
                'execution-info': {
                    'status': 'success'
                },
                'response': response,
            }
            responder(resp_message)
    except Exception as e:
        logging.exception('Unhandled exception')
        resp_message = {
            'execution-info': {
                'status': 'error',
                # TODO: Only ouput message if it is an exception generated
                # by us
                'reason': str(e),
            }
        }
        responder(resp_message)

    ch.basic_ack(delivery_tag=method.delivery_tag)


def run():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=config.RABBITMQ_HOST))
    channel = connection.channel()

    channel.exchange_declare(exchange=EXCHANGE_NAME, exchange_type='direct')

    # let rabbitmq define a name for the exclusive queue
    result = channel.queue_declare(queue='', exclusive=True)
    exclusive_queue_name = result.method.queue
    # setup one queue that is shared by all consumers
    channel.queue_declare(queue=COMPETING_QUEUE)

    for queue, commands in QUEUE_COMMANDS_MAP.items():
        if queue == '':
            queue = exclusive_queue_name

        for command in commands:
            channel.queue_bind(
                exchange=EXCHANGE_NAME, queue=queue, routing_key=command)

    systemd_path = Path.home() / '.config/systemd/user'
    service_manager = services.SystemdServiceManager(systemd_path)

    # TODO: Setup or radvd does not belong here, we will remove it
    # Guest VPNs have to handle IPv6 management on their own
    radvd = aetherscale.vpn.radvd.Radvd(
        config.AETHERSCALE_CONFIG_DIR / 'radvd.conf', config.VPN_48_PREFIX)
    service_manager.install_simple_service(
        radvd.get_start_command(), service_name=RADVD_SERVICE_NAME,
        description='IPv6 Router Advertisment for VPNs')
    service_manager.start_service(RADVD_SERVICE_NAME)

    handler = ComputingHandler(radvd, service_manager)

    bound_callback = lambda ch, method, properties, body: \
        callback(ch, method, properties, body, handler)
    channel.basic_consume(
        queue=exclusive_queue_name, on_message_callback=bound_callback)
    channel.basic_consume(
        queue=COMPETING_QUEUE, on_message_callback=bound_callback)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print('Keyboard interrupt, stopping service')
