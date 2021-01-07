import logging
import os
from pathlib import Path
import pwd
import socket


LOG_LEVEL = os.getenv('LOG_LEVEL', default=logging.WARNING)

HOSTNAME = os.getenv('HOSTNAME', default=socket.gethostname())

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', default='localhost')

BASE_IMAGE_FOLDER = Path(os.getenv('BASE_IMAGE_FOLDER', default='base_images'))
USER_IMAGE_FOLDER = Path(os.getenv('USER_IMAGE_FOLDER', default='user_images'))

AETHERSCALE_CONFIG_DIR = Path.home() / '.config/aetherscale'
(AETHERSCALE_CONFIG_DIR / 'networking').mkdir(parents=True, exist_ok=True)

NETWORK_IP = os.getenv('NETWORK_IP', default='192.168.0.1/24')
NETWORK_GATEWAY = os.getenv('NETWORK_GATEWAY', default='192.168.0.1')
NETWORK_PHYSICAL_DEVICE = os.getenv('NETWORK_PHYSICAL_DEVICE', default='eth0')

VPN_CONFIG_FOLDER = AETHERSCALE_CONFIG_DIR / 'tinc'
VPN_NUM_PREPARED_INTERFACES = 2
VPN_48_PREFIX = 'fde7:2361:234a'
VPN_PORTS = set(range(50000, 51000))

USER = pwd.getpwuid(os.getuid()).pw_name
