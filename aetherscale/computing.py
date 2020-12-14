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
from .qemu import image, runtime
from .qemu.exceptions import QemuException
from . import config
from . import services


VDE_FOLDER = '/tmp/vde.ctl'
VDE_TAP_INTERFACE = 'tap-vde'

EXCHANGE_NAME = 'computing'
COMPETING_QUEUE = 'computing-competing'
QUEUE_COMMANDS_MAP = {
    '': ['list-vms', 'start-vm', 'stop-vm', 'delete-vm'],
    COMPETING_QUEUE: ['create-vm'],
}

logging.basicConfig(level=config.LOG_LEVEL)


def user_image_path(vm_id: str) -> Path:
    return config.USER_IMAGE_FOLDER / f'{vm_id}.qcow2'


def qemu_socket_monitor(vm_id: str) -> Path:
    return Path(f'/tmp/aetherscale-qmp-{vm_id}.sock')


def qemu_socket_guest_agent(vm_id: str) -> Path:
    return Path(f'/tmp/aetherscale-qga-{vm_id}.sock')


def create_user_image(vm_id: str, image_name: str) -> Path:
    base_image = config.BASE_IMAGE_FOLDER / f'{image_name}.qcow2'
    print(base_image)
    if not base_image.is_file():
        raise IOError(f'Image "{image_name}" does not exist')

    user_image = user_image_path(vm_id)

    create_img_result = subprocess.run([
        'qemu-img', 'create', '-f', 'qcow2',
        '-b', str(base_image.absolute()), '-F', 'qcow2', str(user_image)])
    if create_img_result.returncode != 0:
        raise QemuException(f'Could not create image for VM "{vm_id}"')

    return user_image


@dataclass
class QemuStartupConfig:
    vm_id: str
    hda_image: Path
    mac_addr: str
    vde_folder: Path


class ComputingHandler:
    def __init__(self, service_manager: services.ServiceManager):
        self.service_manager = service_manager

    def list_vms(self, _: Dict[str, Any]) -> List[Dict[str, Any]]:
        vms = []

        for proc in psutil.process_iter(['pid', 'name']):
            if proc.name().startswith('vm-'):
                vm_id = proc.name()[3:]

                socket_file = qemu_socket_guest_agent(vm_id)
                hint = None
                ip_addresses = []
                try:
                    fetcher = runtime.GuestAgentIpAddress(socket_file)
                    ip_addresses = fetcher.fetch_ip_addresses()
                except QemuException:
                    hint = 'Could not retrieve IP address for guest'

                msg = {
                    'vm-id': vm_id,
                    'ip-addresses': ip_addresses,
                }
                if hint:
                    msg['hint'] = hint

                vms.append(msg)

        return vms

    def create_vm(self, options: Dict[str, Any]) -> Dict[str, str]:
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

        if 'init-script' in options:
            with image.guestmount(user_image) as guest_fs:
                image.install_startup_script(options['init-script'], guest_fs)

        mac_addr = interfaces.create_mac_address()
        logging.debug(f'Assigning MAC address "{mac_addr}" to VM "{vm_id}"')

        qemu_config = QemuStartupConfig(
            vm_id=vm_id,
            hda_image=user_image,
            mac_addr=mac_addr,
            vde_folder=Path(VDE_FOLDER))
        unit_name = systemd_unit_name_for_vm(vm_id)
        self._create_qemu_systemd_unit(unit_name, qemu_config)
        self.service_manager.start_service(unit_name)

        logging.info(f'Started VM "{vm_id}"')
        return {
            'status': 'starting',
            'vm-id': vm_id,
        }

    def start_vm(self, options: Dict[str, Any]) -> Dict[str, str]:
        try:
            vm_id = options['vm-id']
        except KeyError:
            raise ValueError('VM ID not specified')

        unit_name = systemd_unit_name_for_vm(vm_id)

        if not self.service_manager.service_exists(unit_name):
            raise RuntimeError('VM does not exist')
        elif self.service_manager.service_is_running(unit_name):
            response = {
                'status': 'starting',
                'vm-id': vm_id,
                'hint': f'VM "{vm_id}" was already started',
            }
        else:
            self.service_manager.start_service(unit_name)
            self.service_manager.enable_service(unit_name)

            response = {
                'status': 'starting',
                'vm-id': vm_id,
            }

        return response

    def stop_vm(self, options: Dict[str, Any]) -> Dict[str, str]:
        try:
            vm_id = options['vm-id']
        except KeyError:
            raise ValueError('VM ID not specified')

        kill_flag = bool(options.get('kill', False))
        stop_status = 'killed' if kill_flag else 'stopped'

        unit_name = systemd_unit_name_for_vm(vm_id)

        if not self.service_manager.service_exists(unit_name):
            raise RuntimeError('VM does not exist')
        elif not self.service_manager.service_is_running(unit_name):
            response = {
                'status': stop_status,
                'vm-id': vm_id,
                'hint': f'VM "{vm_id}" was not running',
            }
        else:
            self.service_manager.disable_service(unit_name)

            if kill_flag:
                self.service_manager.stop_service(unit_name)
            else:
                qemu_socket = qemu_socket_monitor(vm_id)
                qm = runtime.QemuMonitor(
                    qemu_socket, protocol=runtime.QemuProtocol.QMP)
                qm.execute('system_powerdown')

            response = {
                'status': stop_status,
                'vm-id': vm_id,
            }

        return response

    def delete_vm(self, options: Dict[str, Any]) -> Dict[str, str]:
        try:
            vm_id = options['vm-id']
        except KeyError:
            raise ValueError('VM ID not specified')

        # force kill stop when a VM is deleted
        options['kill'] = True
        self.stop_vm(options)

        unit_name = systemd_unit_name_for_vm(vm_id)
        user_image = user_image_path(vm_id)

        self.service_manager.uninstall_service(unit_name)
        user_image.unlink()

        return {
            'status': 'deleted',
            'vm-id': vm_id,
        }

    def _create_qemu_systemd_unit(
            self, unit_name: str, qemu_config: QemuStartupConfig):
        hda_quoted = shlex.quote(str(qemu_config.hda_image.absolute()))
        device_quoted = shlex.quote(
            f'virtio-net-pci,netdev=pubnet,mac={qemu_config.mac_addr}')
        netdev_quoted = shlex.quote(
            f'vde,id=pubnet,sock={str(qemu_config.vde_folder)}')
        name_quoted = shlex.quote(
            f'qemu-vm-{qemu_config.vm_id},process=vm-{qemu_config.vm_id}')

        qemu_monitor_path = qemu_socket_monitor(qemu_config.vm_id)
        socket_quoted = shlex.quote(f'unix:{qemu_monitor_path},server,nowait')

        qga_monitor_path = qemu_socket_guest_agent(qemu_config.vm_id)
        qga_chardev_quoted = shlex.quote(
            f'socket,path={qga_monitor_path},server,nowait,id=qga0')

        command = \
            f'qemu-system-x86_64 -m 4096 -accel kvm -hda {hda_quoted} ' \
            f'-device {device_quoted} -netdev {netdev_quoted} ' \
            f'-name {name_quoted} ' \
            '-nographic ' \
            f'-qmp {socket_quoted} ' \
            f'-chardev {qga_chardev_quoted} ' \
            '-device virtio-serial ' \
            '-device virtserialport,chardev=qga0,name=org.qemu.guest_agent.0'

        with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as f:
            f.write('[Unit]\n')
            f.write(f'Description=aetherscale VM {qemu_config.vm_id}\n')
            f.write('\n')
            f.write('[Service]\n')
            f.write(f'ExecStart={command}\n')
            f.write('\n')
            f.write('[Install]\n')
            f.write('WantedBy=default.target\n')

        self.service_manager.install_service(Path(f.name), unit_name)
        os.remove(f.name)


def get_process_for_vm(vm_id: str) -> Optional[psutil.Process]:
    for proc in psutil.process_iter(['name']):
        if proc.name() == vm_id:
            return proc

    return None


def systemd_unit_name_for_vm(vm_id: str) -> str:
    return f'aetherscale-vm-{vm_id}.service'


def callback(ch, method, properties, body, handler: ComputingHandler):
    command_fn: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
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
    handler = ComputingHandler(service_manager)

    bound_callback = lambda ch, method, properties, body: \
        callback(ch, method, properties, body, handler)
    channel.basic_consume(
        queue=exclusive_queue_name, on_message_callback=bound_callback)
    channel.basic_consume(
        queue=COMPETING_QUEUE, on_message_callback=bound_callback)

    # a TAP interface for VDE must already have been created
    if not interfaces.check_device_existence(VDE_TAP_INTERFACE):
        logging.error(
            f'Interface {VDE_TAP_INTERFACE} does not exist. '
            'Please create it manually and then start this service again')
        sys.exit(1)

    logging.info('Bringing up VDE networking')
    service_manager.install_service(
        Path('data/systemd/aetherscale-vde.service'),
        'aetherscale-vde.service')
    service_manager.start_service('aetherscale-vde.service')
    # Give systemd a bit time to start VDE
    time.sleep(0.5)
    if not service_manager.service_is_running('aetherscale-vde.service'):
        logging.error('Failed to start VDE networking.')
        sys.exit(1)

    channel.start_consuming()
