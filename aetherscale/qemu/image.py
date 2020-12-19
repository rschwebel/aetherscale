from contextlib import contextmanager
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import List, TextIO, Iterator

from aetherscale.execution import run_command_chain
from aetherscale.qemu.exceptions import QemuException
import aetherscale.timing


STARTUP_FILENAME = 'aetherscale-init'


@contextmanager
def guestmount(image_path: Path) -> Iterator[Path]:
    mount_dir = tempfile.mkdtemp()

    logging.debug(f'Mounting {image_path} at {mount_dir}')
    try:
        success = run_command_chain([
            ['guestmount', '-a', str(image_path.absolute()), '-i', mount_dir]])

        if not success:
            raise QemuException(f'Could not mount image {image_path}')

        yield Path(mount_dir)
    finally:
        logging.debug(f'Unmounting {mount_dir}')
        run_command_chain([['guestunmount', mount_dir]])
        os.rmdir(mount_dir)

        # It seems image is not released immediately after guestunmount returns
        # thus we have to wait until write-lock is released, but at most k
        # seconds
        with aetherscale.timing.timeout(seconds=5):
            logging.debug(f'Waiting for write lock to get released')

            access_ok = False
            while not access_ok:
                # qemu-img info fails if write lock cannot be retrieved
                result = subprocess.run(['qemu-img', 'info', str(image_path)])
                access_ok = result.returncode == 0


def install_startup_script(script_source: str, mount_dir: Path):
    startup_service_path = \
        mount_dir / f'etc/systemd/system/{STARTUP_FILENAME}.service'
    with open(startup_service_path, 'wt') as f:
        create_systemd_startup_unit(f, Path(f'/root/{STARTUP_FILENAME}.sh'))

    multi_user_target_path = \
        mount_dir / f'etc/systemd/system/multi-user.target.wants'
    multi_user_target_path.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile('wt') as startup_script:
        startup_script.write(script_source)
        startup_script.flush()

        executable_target = mount_dir / f'root/{STARTUP_FILENAME}.sh'
        shutil.copyfile(startup_script.name, executable_target)
        os.symlink(
            f'/etc/systemd/system/{STARTUP_FILENAME}.service',
            multi_user_target_path / f'{STARTUP_FILENAME}.service')

        os.chmod(executable_target, 0o755)


def create_systemd_startup_unit(
        f: TextIO, startup_script: Path):
    logging.debug(f'Creating systemd init-script service at {startup_script}')

    condition_file = f'/root/{STARTUP_FILENAME}.done'

    f.write('[Unit]\n')
    f.write('Description=aetherscale VM init script\n')
    f.write(f'ConditionPathExists=!{condition_file}\n')
    f.write('\n')
    f.write('[Service]\n')
    f.write('Type=oneshot\n')
    # minus means: always execute the second command, independent from success
    # state of first script
    f.write(f'ExecStart=-{str(startup_script)}\n')
    f.write(f'ExecStart=/bin/touch {condition_file}\n')
    f.write('\n')
    f.write('[Install]\n')
    f.write('WantedBy=multi-user.target\n')
