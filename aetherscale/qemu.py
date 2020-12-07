import json
from pathlib import Path
import socket
from typing import Any


class QemuMonitor:
    def __init__(self, socket_file: Path):
        # TODO: It's not really nice that we use the file object
        # to read lines and the socket to write
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(socket_file))
        self.f = self.sock.makefile('rw')

        # Initialize connection immediately
        self._initialize()

    def execute(self, command: str) -> Any:
        json_line = json.dumps({'execute': command}) + '\n'
        self.sock.sendall(json_line.encode('utf-8'))
        return json.loads(self.f.readline())

    def _initialize(self):
        # Read the capabilities
        self.f.readline()

        # Acknowledge the QMP capability negotiation
        self.execute('qmp_capabilities')
