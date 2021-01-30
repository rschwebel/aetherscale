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
    img_file = directory / f'{random_name}.qcow2'
    try:
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

        handler = computing.ComputingHandler(
            radvd=mock.MagicMock(), service_manager=mock_service_manager)

        with base_image(tmppath) as img:
            results = list(handler.create_vm({'image': img.stem}))
            list_results = list(handler.list_vms({}))
            vm_id = results[0]['vm-id']
            service_name = computing.systemd_unit_name_for_vm(vm_id)
            assert results[0]['status'] == 'allocating'
            assert results[1]['status'] == 'starting'
            assert mock_service_manager.service_is_running(service_name)
            assert list_results[0][0]['vm-id'] == vm_id

            # TODO: Test graceful stop, needs mock of QemuMonitor
            results = list(handler.stop_vm({'vm-id': vm_id, 'kill': True}))
            list_results = list(handler.list_vms({}))
            assert results[0]['status'] == 'killed'
            assert mock_service_manager.service_exists(service_name)
            assert not mock_service_manager.service_is_running(service_name)
            assert list_results[0][0]['vm-id'] == vm_id

            results = list(handler.start_vm({'vm-id': vm_id}))
            list_results = list(handler.list_vms({}))
            assert results[0]['status'] == 'starting'
            assert mock_service_manager.service_exists(service_name)
            assert mock_service_manager.service_is_running(service_name)
            assert list_results[0][0]['vm-id'] == vm_id

            results = list(handler.delete_vm({'vm-id': vm_id}))
            list_results = list(handler.list_vms({}))
            assert results[0]['status'] == 'deleted'
            assert not mock_service_manager.service_exists(service_name)
            assert not mock_service_manager.service_is_running(service_name)
            assert len(list_results[0]) == 0


def test_run_missing_base_image(tmppath, mock_service_manager: ServiceManager):
    with mock.patch('aetherscale.config.BASE_IMAGE_FOLDER', tmppath), \
             mock.patch('aetherscale.config.USER_IMAGE_FOLDER', tmppath):

        handler = computing.ComputingHandler(
            radvd=mock.MagicMock(), service_manager=mock_service_manager)

        # specify invalid base image
        with pytest.raises(OSError):
            # make sure to exhaust the iterator
            list(handler.create_vm({'image': 'some-missing-image'}))

        # do not specify a base image
        with pytest.raises(ValueError):
            # make sure to exhaust the iterator
            list(handler.create_vm({}))


def test_vm_id_systemd_unit():
    assert 'myvmid' == computing.vm_id_from_systemd_unit(
        computing.systemd_unit_name_for_vm('myvmid'))
