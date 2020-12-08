import contextlib
import json
from pathlib import Path
import socket
import tempfile
import threading
import uuid

from aetherscale.qemu import QemuMonitor


class MockQemuServer:
    init_msg = {"QMP": {"version": {"qemu": {
        "micro": 0, "minor": 6, "major": 1
    }, "package": ""}, "capabilities": []}}
    mock_ok_response = {'return': {}}

    def __init__(self, socket_file: str):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket_file = socket_file
        self.received_executes = []

    def __enter__(self):
        self._sock.bind(self._socket_file)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sock.close()

    def listen(self):
        self._sock.listen()

        conn, addr = self._sock.accept()
        filelike = conn.makefile('rb')

        self._send_message(self.init_msg, conn)

        try:
            while True:
                msg = self._recv_message(filelike)
                self.received_executes.append(msg['execute'])

                # for now always return with OK status
                self._send_message(self.mock_ok_response, conn)
        except json.JSONDecodeError as e:
            conn.close()

    def _send_message(self, message, conn):
        msg_with_newline = json.dumps(message) + '\r\n'
        conn.send(msg_with_newline.encode('ascii'))

    def _recv_message(self, filelike):
        line = filelike.readline()
        return json.loads(line.decode('utf-8'))


@contextlib.contextmanager
def run_mock_qemu_server(socket_file: str) -> MockQemuServer:
    with MockQemuServer(socket_file) as mock_server:
        t = threading.Thread(target=mock_server.listen)
        t.daemon = True
        t.start()
        yield mock_server


def test_initializes_with_capabilities_acceptance():
    socket_file = Path(tempfile.gettempdir()) / str(uuid.uuid4())

    with run_mock_qemu_server(str(socket_file)) as mock_server:
        QemuMonitor(socket_file)
        assert 'qmp_capabilities' in mock_server.received_executes
