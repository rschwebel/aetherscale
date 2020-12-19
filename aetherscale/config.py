import logging
import os
from pathlib import Path


LOG_LEVEL = os.getenv('LOG_LEVEL', default=logging.WARNING)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', default='localhost')

BASE_IMAGE_FOLDER = Path(os.getenv('BASE_IMAGE_FOLDER', default='base_images'))
USER_IMAGE_FOLDER = Path(os.getenv('USER_IMAGE_FOLDER', default='user_images'))

VPN_CONFIG_FOLDER = Path.home() / '.config/aetherscale/tinc'
VPN_NUM_PREPARED_INTERFACES = 2