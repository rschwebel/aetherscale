import logging
import random
import subprocess
from typing import Optional

from . import execution


class NetworkException(Exception):
    pass


def check_device_existence(device: str) -> bool:
    # if ip link show dev [devicename] does not find [devicename], it will
    # write a message to stderr, but none to stdout
    result = subprocess.run(
        ['ip', 'link', 'show', 'dev', device], stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL)

    if result.stdout:
        return True
    else:
        return False


def init_bridge(
        bridge_device: str, phys_device: str, ip: Optional[str],
        gateway: Optional[str]) -> bool:
    if check_device_existence(bridge_device):
        logging.debug(
            f'Device {bridge_device} already exists, will not re-create')
        return True
    else:
        logging.debug(f'Creating bridge device {bridge_device}')

        commands = [
            ['ip', 'link', 'add', bridge_device, 'type', 'bridge'],
            ['ip', 'link', 'set', bridge_device, 'up'],
            ['ip', 'link', 'set', phys_device, 'up'],
            ['ip', 'link', 'set', phys_device, 'master', bridge_device],
            ['ip', 'addr', 'flush', 'dev', phys_device],
        ]
        if ip:
            commands.append(
                ['ip', 'addr', 'add', ip, 'dev', bridge_device])
        if gateway:
            commands.append(
                ['ip', 'route', 'add', 'default',
                 'via', gateway, 'dev', bridge_device])

        return execution.run_command_chain(commands)


def create_tap_device(
        tap_device_name, bridge_device_name, user) -> bool:
    creation_ok = execution.run_command_chain([
        ['ip', 'tuntap', 'add', 'dev', tap_device_name,
            'mode', 'tap', 'user', user],
        ['ip', 'link', 'set', 'dev', tap_device_name, 'up'],
        ['ip', 'link', 'set', tap_device_name, 'master', bridge_device_name],
    ])

    return creation_ok


def create_mac_address() -> str:
    # Set second least significant bit of leftmost pair to 1 (local)
    # Set least significant bit of leftmost pair to 0 (unicast)
    mac_bits = (random.getrandbits(48) | 0x020000000000) & 0xfeffffffffff
    mac_str = '{:012x}'.format(mac_bits)
    return ':'.join([
        mac_str[:2], mac_str[2:4], mac_str[4:6],
        mac_str[6:8], mac_str[8:10], mac_str[10:],
    ])
