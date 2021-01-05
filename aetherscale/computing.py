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
from typing import List, Optional, Dict, Any, Callable, Tuple

from . import networking
from .qemu import image, runtime
from .qemu.exceptions import QemuException
from . import config
from . import services
from .vpn.tinc import TincVirtualNetwork
import aetherscale.vpn.radvd


VDE_FOLDER = '/tmp/vde.ctl'
VDE_TAP_INTERFACE = 'tap-vde'

EXCHANGE_NAME = 'computing'
COMPETING_QUEUE = 'computing-competing'
QUEUE_COMMANDS_MAP = {
    '': ['list-vms', 'start-vm', 'stop-vm', 'delete-vm'],
    COMPETING_QUEUE: ['create-vm'],
}

RADVD_SERVICE_NAME = 'aetherscale-radvd.service'

logging.basicConfig(level=config.LOG_LEVEL)


def user_image_path(vm_id: str) -> Path:
    return config.USER_IMAGE_FOLDER / f'{vm_id}.qcow2'


def qemu_socket_monitor(vm_id: str) -> Path:
    return Path(f'/tmp/aetherscale-qmp-{vm_id}.sock')


def qemu_socket_guest_agent(vm_id: str) -> Path:
    return Path(f'/tmp/aetherscale-qga-{vm_id}.sock')


def create_user_image(vm_id: str, image_name: str) -> Path:
    base_image = config.BASE_IMAGE_FOLDER / f'{image_name}.qcow2'
    if not base_image.is_file():
        raise IOError(f'Image "{image_name}" does not exist')

    user_image = user_image_path(vm_id)

    create_img_result = subprocess.run([
        'qemu-img', 'create', '-f', 'qcow2',
        '-b', str(base_image.absolute()), '-F', 'qcow2', str(user_image)])
    if create_img_result.returncode != 0:
        raise QemuException(f'Could not create image for VM "{vm_id}"')

    return user_image


def setup_script_path(tap_name: str) -> Path:
    network_conf_dir = config.AETHERSCALE_CONFIG_DIR / 'networking'
    return network_conf_dir / f'{tap_name}-setup.sh'


def teardown_script_path(tap_name: str) -> Path:
    network_conf_dir = config.AETHERSCALE_CONFIG_DIR / 'networking'
    return network_conf_dir / f'{tap_name}-teardown.sh'


def setup_tap_device(tap_name: str, bridge: str) -> Tuple[Path, Path]:
    iproute = networking.Iproute2Network()
    iproute.tap_device(tap_name, config.USER, bridge)

    setup_script = setup_script_path(tap_name)
    teardown_script = teardown_script_path(tap_name)

    with open(setup_script, 'w') as f:
        f.write(iproute.setup_script())
    os.chmod(setup_script, 0o755)

    with open(teardown_script, 'w') as f:
        f.write(iproute.teardown_script())
    os.chmod(teardown_script, 0o755)

    return setup_script, teardown_script


class ComputingHandler:
    def __init__(
            self, radvd: aetherscale.vpn.radvd.Radvd,
            service_manager: services.ServiceManager):

        self.radvd = radvd
        self.service_manager = service_manager

        self.established_vpns: Dict[str, TincVirtualNetwork] = {}

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

        qemu_interfaces = []

        network_setup_scripts = []
        network_teardown_scripts = []

        if 'vpn' in options:
            # TODO: Do we have to assign the VPN mac addr to the macvtap?
            vpn_tap_device = self._establish_vpn(options['vpn'], vm_id)
            network_setup_scripts.append(setup_script_path(vpn_tap_device))
            network_teardown_scripts.append(
                teardown_script_path(vpn_tap_device))

            mac_addr_vpn = networking.create_mac_address()
            logging.debug(
                f'Assigning MAC address "{mac_addr_vpn}" to '
                f'VM "{vm_id}" for VPN')

            privnet = runtime.QemuInterfaceConfig(
                mac_address=mac_addr_vpn,
                type=runtime.QemuInterfaceType.TAP,
                tap_device=vpn_tap_device)
            qemu_interfaces.append(privnet)

        if 'public-ip' in options and options['public-ip']:
            mac_addr = networking.create_mac_address()
            logging.debug(f'Assigning MAC address "{mac_addr}" to VM "{vm_id}"')

            pub_tap_device = f'pub-{vm_id}'
            pubnet = runtime.QemuInterfaceConfig(
                mac_address=mac_addr,
                type=runtime.QemuInterfaceType.TAP,
                tap_device=pub_tap_device)
            qemu_interfaces.append(pubnet)

            setup_script, teardown_script = setup_tap_device(
                pub_tap_device, 'br0')
            network_setup_scripts.append(setup_script)
            network_teardown_scripts.append(teardown_script)

        qemu_config = runtime.QemuStartupConfig(
            vm_id=vm_id,
            hda_image=user_image,
            interfaces=qemu_interfaces)

        unit_name = systemd_unit_name_for_vm(vm_id)
        self._create_qemu_systemd_unit(
            unit_name, qemu_config,
            network_setup_scripts, network_teardown_scripts)
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
        # TODO: Once all VMs of a VPN on a host have been deleted, we can delete
        # the associated VPN

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
            self, unit_name: str, qemu_config: runtime.QemuStartupConfig,
            setup_scripts: List[Path], teardown_scripts: List[Path]):
        qemu_name = \
            f'qemu-vm-{qemu_config.vm_id},process=vm-{qemu_config.vm_id}'
        qemu_monitor_path = qemu_socket_monitor(qemu_config.vm_id)
        qga_monitor_path = qemu_socket_guest_agent(qemu_config.vm_id)
        qga_chardev = f'socket,path={qga_monitor_path},server,nowait,id=qga0'

        command = [
            'qemu-system-x86_64',
            '-nographic',
            '-cpu', 'host',
            '-m', '4096',
            '-accel', 'kvm',
            '-hda', str(qemu_config.hda_image.absolute()),
            '-name', qemu_name,
            '-qmp', f'unix:{qemu_monitor_path},server,nowait',
            '-chardev', qga_chardev,
            '-device', 'virtio-serial',
            '-device',
            'virtserialport,chardev=qga0,name=org.qemu.guest_agent.0',
        ]

        for i, interface in enumerate(qemu_config.interfaces):
            device = \
                f'virtio-net-pci,netdev=net{i},mac={interface.mac_address}'

            if interface.type == runtime.QemuInterfaceType.VDE:
                netdev = f'vde,id=net{i},sock={str(interface.vde_folder)}'
            elif interface.type == runtime.QemuInterfaceType.TAP:
                netdev = \
                    f'tap,id=net{i},ifname={interface.tap_device},' \
                    'script=no,downscript=no'
            else:
                raise QemuException(
                    f'Unknown interface type "{interface.type}"')

            command += ['-device', device, '-netdev', netdev]

        command = [shlex.quote(arg) for arg in command]
        command = ' '.join(command)

        with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as f:
            f.write('[Unit]\n')
            f.write(f'Description=aetherscale VM {qemu_config.vm_id}\n')
            f.write('\n')
            f.write('[Service]\n')
            for script in setup_scripts:
                f.write(f'ExecStartPre={script.absolute()}\n')
            f.write(f'ExecStart={command}\n')
            for script in teardown_scripts:
                f.write(f'ExecStopPost={script.absolute()}\n')
            f.write('\n')
            f.write('[Install]\n')
            f.write('WantedBy=default.target\n')

        self.service_manager.install_service(Path(f.name), unit_name)
        os.remove(f.name)

    def _establish_vpn(self, vpn_name: str, vm_id: str) -> str:
        vpn_network_prefix = self.radvd.generate_prefix()

        if vpn_name in self.established_vpns:
            vpn = self.established_vpns[vpn_name]
        else:
            logging.info(f'Creating VPN {vpn_name} for VM {vm_id}')

            vpn = TincVirtualNetwork(
                vpn_name, config.VPN_CONFIG_FOLDER, self.service_manager)
            vpn.create_config(config.HOSTNAME)
            vpn.gen_keypair()

            # Create an uninitialized tap device so that tincd can run
            # without root permissions
            # TODO: Assign a more reasonable IP address
            # TODO: In real environments the host does not have to be exposed,
            # this is only because I want to proxy IP traffic from the host to
            # the guest
            host_vpn_ip = vpn_network_prefix.replace('/64', '1')
            iproute = networking.Iproute2Network()
            iproute.tap_device(vpn.interface_name, aetherscale.config.USER)
            iproute.bridged_network(
                vpn.bridge_interface_name, vpn.interface_name,
                ip=host_vpn_ip, flush_ip_device=False)
            setup_network_script = iproute.setup_script()
            teardown_network_script = iproute.teardown_script()

            vpn.start_daemon(setup_network_script, teardown_network_script)

            self.established_vpns[vpn_name] = vpn

            # Setup radvd for IPv6 auto-configuration
            self.radvd.add_interface(
                vpn.bridge_interface_name, vpn_network_prefix)
            self.service_manager.restart_service(RADVD_SERVICE_NAME)
            logging.debug(
                f'Added device {vpn.bridge_interface_name} to radvd '
                f'with IPv6 address range {vpn_network_prefix}')

        # Create a new tap device for the VM to use
        associated_tap_device = 'vpn-' + vm_id
        setup_tap_device(associated_tap_device, vpn.bridge_interface_name)

        logging.debug(
            f'Created TAP device {associated_tap_device} for VM {vm_id}')

        return associated_tap_device


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
        logging.exception('Unhandled exception')
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

    # a TAP interface for VDE must already have been created
    vde_tap_iproute = networking.Iproute2Network()

    if not networking.Iproute2Network.check_device_existence(VDE_TAP_INTERFACE):
        vde_tap_iproute.bridged_network(
            'br0', config.NETWORK_PHYSICAL_DEVICE,
            config.NETWORK_IP, config.NETWORK_GATEWAY,
            flush_ip_device=True)
        vde_tap_iproute.tap_device(VDE_TAP_INTERFACE, config.USER, 'br0')

        if not vde_tap_iproute.setup():
            print('Could not setup VDE tap device', file=sys.stderr)
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

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print('Keyboard interrupt, stopping service')
        vde_tap_iproute.teardown()
