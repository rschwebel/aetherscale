from pathlib import Path
import tempfile
from unittest import mock

from aetherscale.services import SystemdServiceManager


def test_systemd_creates_file(tmppath: Path):
    systemd = SystemdServiceManager(tmppath)
    with tempfile.NamedTemporaryFile('wt') as f:
        f.write('[Unit]')
        f.flush()

        systemd.install_service(Path(f.name), 'test.service')
        assert systemd.service_exists('test.service')
        assert (tmppath / 'test.service').is_file()

        systemd.uninstall_service('test.service')
        assert not (tmppath / 'test.service').is_file()
        assert not systemd.service_exists('test.service')


@mock.patch('subprocess.run')
def test_systemd_calls_system_binary(subprocess_run, tmppath):
    systemd = SystemdServiceManager(tmppath)

    keyword_pairs = [
        (systemd.enable_service, 'enable'),
        (systemd.disable_service, 'disable'),
        (systemd.start_service, 'start'),
        (systemd.stop_service, 'stop'),
        (systemd.service_is_running, 'is-active'),
    ]

    # we don't want to check the exact call as this might be valid in some
    # different forms; but we want to make sure that at least the right
    # keywords are inside the command
    for function, keyword in keyword_pairs:
        function('test.service')
        assert 'systemctl' in subprocess_run.call_args[0][0]
        assert keyword in subprocess_run.call_args[0][0]
