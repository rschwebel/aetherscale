import logging
from pathlib import Path
import shutil
import subprocess
from typing import List


def run_command_chain(commands: List[List[str]]) -> bool:
    for command in commands:
        logging.debug(f'Running command: {" ".join(command)}')
        result = subprocess.run(command)

        if result.returncode != 0:
            return False

    return True


def copy_systemd_unit(unit_file: Path, unit_name: str):
    if '.' not in unit_name:
        raise ValueError('Unit name must contain the suffix, e.g. .service')

    systemd_unit_dir = Path().home() / '.config/systemd/user'
    systemd_unit_dir.mkdir(parents=True, exist_ok=True)
    target_unit_file = systemd_unit_dir / unit_name

    shutil.copyfile(unit_file, target_unit_file)

    # Reload system
    subprocess.run(['systemctl', '--user', 'daemon-reload'])


def start_systemd_unit(unit_name: str) -> bool:
    return run_command_chain([
        ['systemctl', '--user', 'start', unit_name],
    ])


def enable_systemd_unit(unit_name: str) -> bool:
    return run_command_chain([
        ['systemctl', '--user', 'enable', unit_name],
    ])


def systemctl_is_running(unit_name: str) -> bool:
    result = subprocess.run([
        'systemctl', '--user', 'is-active', '--quiet', unit_name])
    return result.returncode == 0
