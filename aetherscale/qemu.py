import json
from pathlib import Path
import socket
from typing import Any


class QemuMonitor:
    # TODO: Improve QMP communication, spec is here:
    # https://github.com/qemu/qemu/blob/master/docs/interop/qmp-spec.txt
    def __init__(self, socket_file: Path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(socket_file))
        self.f = self.sock.makefile('rw')

        # Initialize connection immediately
        self._initialize()

    def execute(self, command: str) -> Any:
        json_line = json.dumps({'execute': command}) + '\r\n'
        self.sock.sendall(json_line.encode('utf-8'))
        return json.loads(self.f.readline())

    def _initialize(self):
        # Read the capabilities
        self.f.readline()

        # Acknowledge the QMP capability negotiation
        self.execute('qmp_capabilities')
