from dataclasses import dataclass
import logging
import json
import os
from pathlib import Path
import pika
import psutil
import random
import shlex
import string
import subprocess
import sys
import tempfile
import time
from typing import List, Optional, Dict, Any, Callable

from . import interfaces
from . import execution
from . import qemu
from .config import LOG_LEVEL, RABBITMQ_HOST


VDE_FOLDER = '/tmp/vde.ctl'
VDE_TAP_INTERFACE = 'tap-vde'

BASE_IMAGE_FOLDER = Path('base_images')
USER_IMAGE_FOLDER = Path('user_images')

EXCHANGE_NAME = 'computing'
COMPETING_QUEUE = 'computing-competing'
QUEUE_COMMANDS_MAP = {
    '': ['list-vms', 'start-vm', 'stop-vm', 'delete-vm'],
    COMPETING_QUEUE: ['create-vm'],
}

logging.basicConfig(level=LOG_LEVEL)


class QemuException(Exception):
    pass


def user_image_path(vm_id: str) -> Path:
    return USER_IMAGE_FOLDER / f'{vm_id}.qcow2'


def qemu_socket_monitor(vm_id: str) -> Path:
    return Path(f'/tmp/aetherscale-qmp-{vm_id}.sock')


def create_user_image(vm_id: str, image_name: str) -> Path:
    base_image = BASE_IMAGE_FOLDER / f'{image_name}.qcow2'
    if not base_image.is_file():
        raise IOError(f'Image "{image_name}" does not exist')

    user_image = user_image_path(vm_id)

    create_img_result = subprocess.run([
        'qemu-img', 'create', '-f', 'qcow2',
        '-b', str(base_image.absolute()), '-F', 'qcow2', str(user_image)])
    if create_img_result.returncode != 0:
        raise QemuException(f'Could not create image for VM "{vm_id}"')

    return user_image


def list_vms(_: Dict[str, Any]) -> List[str]:
    vms = []

    for proc in psutil.process_iter(['pid', 'name']):
        if proc.name().startswith('vm-'):
            vms.append(proc.name())

    return vms


def create_vm(options: Dict[str, Any]) -> Dict[str, str]:
    vm_id = ''.join(
        random.choice(string.ascii_lowercase) for _ in range(8))
    logging.info(f'Starting VM "{vm_id}"')

    try:
        image_name = os.path.basename(options['image'])
    except KeyError:
        raise ValueError('Image not specified')

    try:
        user_image = create_user_image(vm_id, image_name)
    except (OSError, QemuException):
        raise

    mac_addr = interfaces.create_mac_address()
    logging.debug(f'Assigning MAC address "{mac_addr}" to VM "{vm_id}"')

    qemu_config = QemuStartupConfig(
        vm_id=vm_id,
        hda_image=user_image,
        mac_addr=mac_addr,
        vde_folder=Path(VDE_FOLDER))
    unit_name = systemd_unit_name_for_vm(vm_id)
    create_qemu_systemd_unit(unit_name, qemu_config)
    execution.start_systemd_unit(unit_name)

    logging.info(f'Started VM "{vm_id}"')
    return {
        'status': 'starting',
        'vm-id': vm_id,
    }


def start_vm(options: Dict[str, Any]) -> Dict[str, str]:
    try:
        vm_id = options['vm-id']
    except KeyError:
        raise ValueError('VM ID not specified')

    unit_name = systemd_unit_name_for_vm(vm_id)

    if not execution.systemd_unit_exists(unit_name):
        raise RuntimeError('VM does not exist')
    elif execution.systemctl_is_running(unit_name):
        response = {
            'status': 'starting',
            'vm-id': vm_id,
            'hint': f'VM "{vm_id}" was already started',
        }
    else:
        execution.start_systemd_unit(unit_name)
        execution.enable_systemd_unit(unit_name)

        response = {
            'status': 'starting',
            'vm-id': vm_id,
        }

    return response


def stop_vm(options: Dict[str, Any]) -> Dict[str, str]:
    try:
        vm_id = options['vm-id']
    except KeyError:
        raise ValueError('VM ID not specified')

    kill_flag = bool(options.get('kill', False))
    stop_status = 'killed' if kill_flag else 'stopped'

    unit_name = systemd_unit_name_for_vm(vm_id)

    if not execution.systemd_unit_exists(unit_name):
        raise RuntimeError('VM does not exist')
    elif not execution.systemctl_is_running(unit_name):
        response = {
            'status': stop_status,
            'vm-id': vm_id,
            'hint': f'VM "{vm_id}" was not running',
        }
    else:
        execution.disable_systemd_unit(unit_name)

        if kill_flag:
            execution.stop_systemd_unit(unit_name)
        else:
            qemu_socket = qemu_socket_monitor(vm_id)
            qm = qemu.QemuMonitor(qemu_socket)
            qm.execute('system_powerdown')

        response = {
            'status': stop_status,
            'vm-id': vm_id,
        }

    return response


def delete_vm(options: Dict[str, Any]) -> Dict[str, str]:
    try:
        vm_id = options['vm-id']
    except KeyError:
        raise ValueError('VM ID not specified')

    # force kill stop when a VM is deleted
    options['kill'] = True
    stop_vm(options)

    unit_name = systemd_unit_name_for_vm(vm_id)
    user_image = user_image_path(vm_id)

    execution.delete_systemd_unit(unit_name)
    user_image.unlink()

    return {
        'status': 'deleted',
        'vm-id': vm_id,
    }


def get_process_for_vm(vm_id: str) -> Optional[psutil.Process]:
    for proc in psutil.process_iter(['name']):
        if proc.name() == vm_id:
            return proc

    return None


def systemd_unit_name_for_vm(vm_id: str) -> str:
    return f'aetherscale-vm-{vm_id}.service'


@dataclass
class QemuStartupConfig:
    vm_id: str
    hda_image: Path
    mac_addr: str
    vde_folder: Path


def create_qemu_systemd_unit(
        unit_name: str, qemu_config: QemuStartupConfig):
    hda_quoted = shlex.quote(str(qemu_config.hda_image.absolute()))
    device_quoted = shlex.quote(
        f'virtio-net-pci,netdev=pubnet,mac={qemu_config.mac_addr}')
    netdev_quoted = shlex.quote(
        f'vde,id=pubnet,sock={str(qemu_config.vde_folder)}')
    name_quoted = shlex.quote(
        f'qemu-vm-{qemu_config.vm_id},process=vm-{qemu_config.vm_id}')

    qemu_monitor_path = qemu_socket_monitor(qemu_config.vm_id)
    socket_quoted = shlex.quote(f'unix:{qemu_monitor_path},server,nowait')

    command = f'qemu-system-x86_64 -m 4096 -accel kvm -hda {hda_quoted} ' \
        f'-device {device_quoted} -netdev {netdev_quoted} ' \
        f'-name {name_quoted} ' \
        '-nographic ' \
        f'-qmp {socket_quoted}'

    with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as f:
        f.write('[Unit]\n')
        f.write(f'Description=aetherscale VM {qemu_config.vm_id}\n')
        f.write('\n')
        f.write('[Service]\n')
        f.write(f'ExecStart={command}\n')
        f.write('\n')
        f.write('[Install]\n')
        f.write('WantedBy=default.target\n')

    execution.copy_systemd_unit(Path(f.name), unit_name)
    os.remove(f.name)


def callback(ch, method, properties, body):
    command_fn: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
        'list-vms': list_vms,
        'create-vm': create_vm,
        'start-vm': start_vm,
        'stop-vm': stop_vm,
        'delete-vm': delete_vm,
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

    options = data.get('options', {})
    try:
        response = fn(options)
        # if a function wants to return a response
        # set its execution status to success
        resp_message = {
            'execution-info': {
                'status': 'success'
            },
            'response': response,
        }
    except Exception as e:
        resp_message = {
            'execution-info': {
                'status': 'error',
                # TODO: Only ouput message if it is an exception generated by us
                'reason': str(e),
            }
        }

    ch.basic_ack(delivery_tag=method.delivery_tag)

    if properties.reply_to:
        ch.basic_publish(
            exchange='',
            routing_key=properties.reply_to,
            properties=pika.BasicProperties(
                correlation_id=properties.correlation_id
            ),
            body=json.dumps(resp_message))


def run():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=RABBITMQ_HOST))
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

    channel.basic_consume(
        queue=exclusive_queue_name, on_message_callback=callback)
    channel.basic_consume(
        queue=COMPETING_QUEUE, on_message_callback=callback)

    # a TAP interface for VDE must already have been created
    if not interfaces.check_device_existence(VDE_TAP_INTERFACE):
        logging.error(
            f'Interface {VDE_TAP_INTERFACE} does not exist. '
            'Please create it manually and then start this service again')
        sys.exit(1)

    logging.info('Bringing up VDE networking')
    execution.copy_systemd_unit(
        Path('data/systemd/aetherscale-vde.service'),
        'aetherscale-vde.service')
    execution.start_systemd_unit('aetherscale-vde.service')
    # Give systemd a bit time to start VDE
    time.sleep(0.5)
    if not execution.systemctl_is_running('aetherscale-vde.service'):
        logging.error('Failed to start VDE networking.')
        sys.exit(1)

    channel.start_consuming()
