import contextlib
import json
from pathlib import Path
import pytest
import socket
import tempfile
import threading
import uuid

from aetherscale.qemu.runtime import QemuMonitor, QemuProtocol


class MockQemuServer:
    qmp_init_msg = {"QMP": {"version": {"qemu": {
        "micro": 0, "minor": 6, "major": 1
    }, "package": ""}, "capabilities": []}}
    mock_ok_response = {'return': {}}

    def __init__(self, socket_file: str, protocol: QemuProtocol):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket_file = socket_file
        self.received_executes = []
        self.protocol = protocol

    def __enter__(self):
        self._sock.bind(self._socket_file)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sock.close()

    def listen(self):
        self._sock.listen()

        conn, addr = self._sock.accept()
        filelike = conn.makefile('rb')

        if self.protocol == QemuProtocol.QMP:
            self._send_message(self.qmp_init_msg, conn)

        try:
            while True:
                msg = self._recv_message(filelike)
                self.received_executes.append(msg['execute'])

                # for now always return with OK status
                response = self._build_response(msg)
                self._send_message(response, conn)
        except json.JSONDecodeError:
            conn.close()

    def _build_response(self, message):
        if self.protocol == QemuProtocol.QGA:
            if message['execute'] == 'guest-sync':
                return {'return': message['arguments']['id']}

        return self.mock_ok_response

    def _send_message(self, message, conn):
        msg_with_newline = json.dumps(message) + '\r\n'
        conn.send(msg_with_newline.encode('ascii'))

    def _recv_message(self, filelike):
        line = filelike.readline()
        return json.loads(line.decode('utf-8'))


@contextlib.contextmanager
def run_mock_qemu_server(
        socket_file: str, protocol: QemuProtocol) -> MockQemuServer:
    with MockQemuServer(socket_file, protocol) as mock_server:
        t = threading.Thread(target=mock_server.listen)
        t.daemon = True
        t.start()
        yield mock_server


def test_initializes_with_capabilities_acceptance():
    sock_file = Path(tempfile.gettempdir()) / str(uuid.uuid4())

    with run_mock_qemu_server(str(sock_file), QemuProtocol.QMP) as mock_server:
        QemuMonitor(sock_file, QemuProtocol.QMP)
        assert 'qmp_capabilities' in mock_server.received_executes


def test_timeout(timeout):
    sock_file = Path(tempfile.gettempdir()) / str(uuid.uuid4())
    # A QMP protocol client on a Guest Agent server will have to timeout,
    # because it expects to receive a welcome capabilities message from the
    # server

    with run_mock_qemu_server(str(sock_file), QemuProtocol.QGA) as mock_server:  # noqa: F841
        with timeout(1):  # if function does not finish after 1s, error-out
            with pytest.raises(socket.timeout):
                QemuMonitor(sock_file, QemuProtocol.QMP, timeout=0.1)
