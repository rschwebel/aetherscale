import os
from pathlib import Path

from aetherscale.qemu.image import install_startup_script, STARTUP_FILENAME


def test_copies_startup_script_to_vm_dir(tmpdir):
    tmpdir = Path(tmpdir)

    # Create directories that normally exist in mounted OS
    (tmpdir / 'etc/systemd/system').mkdir(parents=True, exist_ok=True)
    (tmpdir / 'root').mkdir(parents=True, exist_ok=True)

    install_startup_script('echo something', tmpdir)

    assert os.path.isfile(tmpdir / f'root/{STARTUP_FILENAME}.sh')
    assert os.path.isfile(
        tmpdir / f'etc/systemd/system/{STARTUP_FILENAME}.service')
