from contextlib import contextmanager
import os
from pathlib import Path
import pytest
import subprocess
from typing import Iterator
from unittest import mock
import uuid

from aetherscale import computing
from aetherscale.services import ServiceManager


@contextmanager
def base_image(directory: Path) -> Iterator[Path]:
    random_name = str(uuid.uuid4())
    try:
        img_file = directory / f'{random_name}.qcow2'
        subprocess.run([
            'qemu-img', 'create', '-f', 'qcow2', str(img_file), '1G'])
        yield img_file
    finally:
        os.unlink(img_file)


def test_create_user_image(tmppath):
    with mock.patch('aetherscale.config.BASE_IMAGE_FOLDER', tmppath), \
            mock.patch('aetherscale.config.USER_IMAGE_FOLDER', tmppath):

        with base_image(tmppath) as img:
            user_image = computing.create_user_image('my-vm-id', img.stem)
            user_image.is_file()


def test_vm_lifecycle(tmppath, mock_service_manager: ServiceManager):
    with mock.patch('aetherscale.config.BASE_IMAGE_FOLDER', tmppath), \
            mock.patch('aetherscale.config.USER_IMAGE_FOLDER', tmppath):

        handler = computing.ComputingHandler(mock_service_manager)
        with base_image(tmppath) as img:
            result = handler.create_vm({'image': img.stem})
            vm_id = result['vm-id']
            service_name = computing.systemd_unit_name_for_vm(vm_id)
            assert result['status'] == 'starting'
            assert mock_service_manager.service_is_running(service_name)

            # TODO: Test graceful stop, needs mock of QemuMonitor
            result = handler.stop_vm({'vm-id': vm_id, 'kill': True})
            assert result['status'] == 'killed'
            assert mock_service_manager.service_exists(service_name)
            assert not mock_service_manager.service_is_running(service_name)

            result = handler.start_vm({'vm-id': vm_id})
            assert result['status'] == 'starting'
            assert mock_service_manager.service_exists(service_name)
            assert mock_service_manager.service_is_running(service_name)

            result = handler.delete_vm({'vm-id': vm_id})
            assert result['status'] == 'deleted'
            assert not mock_service_manager.service_exists(service_name)
            assert not mock_service_manager.service_is_running(service_name)


def test_run_missing_base_image(tmppath, mock_service_manager: ServiceManager):
    with mock.patch('aetherscale.config.BASE_IMAGE_FOLDER', tmppath), \
             mock.patch('aetherscale.config.USER_IMAGE_FOLDER', tmppath):

        handler = computing.ComputingHandler(mock_service_manager)

        # specify invalid base image
        with pytest.raises(OSError):
            handler.create_vm({'image': 'some-missing-image'})

        # do not specify a base image
        with pytest.raises(ValueError):
            handler.create_vm({})
