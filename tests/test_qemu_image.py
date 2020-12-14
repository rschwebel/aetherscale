import os
import pytest

from aetherscale.qemu import image
from aetherscale.qemu.exceptions import QemuException


def test_copies_startup_script_to_vm_dir(tmppath):
    # Create directories that normally exist in mounted OS
    (tmppath / 'etc/systemd/system').mkdir(parents=True, exist_ok=True)
    (tmppath / 'root').mkdir(parents=True, exist_ok=True)

    image.install_startup_script('echo something', tmppath)

    assert os.path.isfile(tmppath / f'root/{image.STARTUP_FILENAME}.sh')
    assert os.path.isfile(
        tmppath / f'etc/systemd/system/{image.STARTUP_FILENAME}.service')


def test_mount_invalid_image(tmppath):
    imagepath = tmppath / 'image.qcow2'
    imagepath.touch()

    with pytest.raises(QemuException):
        with image.guestmount(imagepath):
            pass
