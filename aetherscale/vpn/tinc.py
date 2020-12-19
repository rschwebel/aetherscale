import logging
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from typing import Optional

from aetherscale.services import ServiceManager


class TincVirtualNetwork(object):
    def __init__(
            self, netname: str, config_folder: Path,
            interface_name: str,
            service_manager: ServiceManager):
        if not self._validate_netname(netname):
            raise ValueError(
                f'Invalid name for network provided ("{netname}")')

        self.netname = netname
        self.config_base_folder = config_folder
        self.service_manager = service_manager

        self.assigned_interface_name = interface_name

    def network_exists(self) -> bool:
        return self._net_config_folder().is_dir()

    @property
    def interface_name(self):
        return self.assigned_interface_name

    def create_config(self, hostname: str):
        if not re.match('^[a-z0-9]+$', hostname):
            raise ValueError(f'Invalid hostname provided ("{hostname}")')

        config_dir = self._net_config_folder()
        config_dir.mkdir(parents=True, exist_ok=True)

        with open(config_dir / 'tinc.conf', 'w') as f:
            lines = [
                f'Name = {hostname}\n',
                'Mode = switch\n',
                f'Interface = {self.interface_name}\n',
            ]
            f.writelines(lines)

        self._create_host(hostname, public_ip=None, pubkey=None)

    def add_peer(self, hostname: str, public_ip: str, pubkey: str):
        self._create_host(hostname, public_ip, pubkey)

        with open(self._net_config_folder() / 'tinc.conf', 'a') as f:
            f.write(f'ConnectTo = {hostname}')

    def _create_host(
            self, hostname: str, public_ip: Optional[str],
            pubkey: Optional[str]):
        hosts_dir = self._net_config_folder() / 'hosts'
        os.makedirs(hosts_dir, exist_ok=True)

        with open(hosts_dir / hostname, 'w') as f:
            if public_ip:
                f.write(f'Address = {public_ip}\n')

            if pubkey:
                f.write('\n')
                f.write(pubkey)

    def gen_keypair(self):
        logging.debug('Generating key pair for tinc')
        subprocess.run(
            ['tincd', '-K', '-c', self._net_config_folder()],
            stdin=subprocess.DEVNULL)
        logging.debug('Finished generating key pair')

    def _validate_netname(self, netname: str):
        return re.match('^[a-z0-9]+$', netname)

    def _net_config_folder(self) -> Path:
        return self.config_base_folder / self.netname

    def _service_name(self) -> str:
        return f'tincd-{self.netname}.service'

    def start_daemon(self):
        net_dir_escaped = shlex.quote(str(self._net_config_folder()))

        service_name = self._service_name()

        self.service_manager.install_simple_service(
            command=f'tincd -D -d {net_dir_escaped}',
            service_name=service_name,
            description=f'aetherscale {self.netname} VPN with tincd')

        self.service_manager.start_service(service_name)

    def teardown_tinc_config(self):
        self.service_manager.uninstall_service(self._service_name())
        shutil.rmtree(self._net_config_folder())
