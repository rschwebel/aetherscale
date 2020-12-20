from dataclasses import dataclass
import enum
import logging
import json
from pathlib import Path
import random
import socket
from typing import Any, Dict, Optional, List

from aetherscale.qemu.exceptions import QemuException


class QemuInterfaceType(enum.Enum):
    TAP = enum.auto()
    VDE = enum.auto()


@dataclass
class QemuInterfaceConfig:
    mac_address: str
    type: QemuInterfaceType
    vde_folder: Optional[Path] = None
    tap_device: Optional[str] = None


@dataclass
class QemuStartupConfig:
    vm_id: str
    hda_image: Path
    interfaces: List[QemuInterfaceConfig]


class QemuProtocol(enum.Enum):
    QMP = enum.auto()
    QGA = enum.auto()


class QemuMonitor:
    # TODO: Improve QMP communication, spec is here:
    # https://github.com/qemu/qemu/blob/master/docs/interop/qmp-spec.txt
    def __init__(
            self, socket_file: Path, protocol: QemuProtocol,
            timeout: Optional[float] = None):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(socket_file))
        self.f = self.sock.makefile('rw')
        self.protocol = protocol

        if timeout:
            self.sock.settimeout(timeout)

        # Initialize connection immediately
        self._initialize()

    def execute(
            self, command: str,
            arguments: Optional[Dict[str, Any]] = None) -> Any:
        message = {'execute': command}
        if arguments:
            message['arguments'] = arguments

        json_line = json.dumps(message) + '\r\n'
        logging.debug(f'Sending message to QEMU: {json_line}')
        self.sock.sendall(json_line.encode('utf-8'))
        return json.loads(self.readline())

    def _initialize(self):
        if self.protocol == QemuProtocol.QMP:
            self._initialize_qmp()
        elif self.protocol == QemuProtocol.QGA:
            self._initialize_guest_agent()
        else:
            raise ValueError('Unknown QemuProtocol')

    def _initialize_qmp(self):
        # Read the capabilities
        self.f.readline()

        # Acknowledge the QMP capability negotiation
        self.execute('qmp_capabilities')

    def _initialize_guest_agent(self):
        # make the server flush partial JSON from previous connections
        prepend_byte = b'\xff'
        self.sock.sendall(prepend_byte)

        rand_int = random.randint(100000, 1000000)
        self.execute('guest-sync', {'id': rand_int})

        return json.loads(self.readline())

    def readline(self) -> Any:
        try:
            logging.debug('Waiting for message from QEMU')
            data = self.f.readline()
            logging.debug(f'Received message from QEMU: {data}')
            return data
        except socket.timeout:
            raise QemuException(
                'Could not communicate with QEMU, is QMP server or GA running?')


class GuestAgentIpAddress:
    def __init__(self, socket_file: Path, timeout: float = 1):
        self.comm_channel = QemuMonitor(socket_file, QemuProtocol.QGA, timeout)

    def fetch_ip_addresses(self):
        resp = self.comm_channel.execute('guest-network-get-interfaces')
        return self._parse_ips_from_response(resp)

    def _parse_ips_from_response(self, response):
        ips = []

        try:
            for interface in response['return']:
                for address in interface['ip-addresses']:
                    ips.append(address['ip-address'])

            return ips
        except KeyError:
            return []
