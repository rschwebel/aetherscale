import logging
import os

LOG_LEVEL = os.getenv('LOG_LEVEL', default=logging.WARNING)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', default='localhost')
