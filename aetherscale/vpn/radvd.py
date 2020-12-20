import os
from pathlib import Path
import tempfile

import aetherscale.config


CONFIG_BLOCK = '''interface INTERFACE {
  AdvSendAdvert on;
  MinRtrAdvInterval 3;
  MaxRtrAdvInterval 10;
  prefix PREFIX {
    AdvOnLink on;
    AdvAutonomous on;
    AdvRouterAddr off;
  };
};'''


class RadvdException(Exception):
    pass


class Radvd:
    def __init__(self, config_file: Path, prefix: str):
        if prefix.count(':') != 2:
            raise RadvdException('Prefix must be a /48 prefix')

        self.config_file = config_file
        self.prefix = prefix

        # This is a poor man's method to check prefix overlap; we only
        # check for duplicate prefixes
        self.assigned_prefixes = set()

        # Create an empty configuration file
        if self.config_file.is_file():
            os.chmod(self.config_file, 0o600)

        with open(self.config_file, 'wt') as f:
            f.write('')

    def generate_prefix(self):
        if len(self.assigned_prefixes) >= 65536:
            raise RadvdException('Max number of available networks reached')

        return self.prefix + ':' + str(len(self.assigned_prefixes)) + '::/64'

    def add_interface(self, interface_name: str, prefix: str):
        if prefix in self.assigned_prefixes:
            raise RadvdException(f'Prefix "{prefix}" was already assigned')

        config_block = CONFIG_BLOCK \
            .replace('INTERFACE', interface_name) \
            .replace('PREFIX', prefix)

        # Radvd forces us to have read-only permissions on the file.
        # To be able to edit it, we have to alter permissions and change them
        # back after our changes
        os.chmod(self.config_file, 0o600)

        with open(self.config_file, 'at') as f:
            f.write('\n\n' + config_block)

        self.assigned_prefixes.add(prefix)

        os.chmod(self.config_file, 0o400)

    def get_start_command(self):
        pidfile = Path(tempfile.gettempdir()) / 'radvd.pid'
        return f'/usr/bin/sudo /usr/bin/radvd -n -C {self.config_file} ' \
               f'-u {aetherscale.config.USER} -p {str(pidfile)}'
