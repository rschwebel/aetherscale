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


def systemd_unit_path(unit_name: str) -> Path:
    systemd_unit_dir = Path().home() / '.config/systemd/user'
    return systemd_unit_dir / unit_name


def copy_systemd_unit(unit_file: Path, unit_name: str):
    if '.' not in unit_name:
        raise ValueError('Unit name must contain the suffix, e.g. .service')

    target_unit_path = systemd_unit_path(unit_name)
    target_unit_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(unit_file, target_unit_path)

    # Reload system
    subprocess.run(['systemctl', '--user', 'daemon-reload'])


def delete_systemd_unit(unit_name: str):
    systemd_unit_path(unit_name).unlink(missing_ok=True)


def start_systemd_unit(unit_name: str) -> bool:
    return run_command_chain([
        ['systemctl', '--user', 'start', unit_name],
    ])


def stop_systemd_unit(unit_name: str) -> bool:
    return run_command_chain([
        ['systemctl', '--user', 'stop', unit_name],
    ])


def enable_systemd_unit(unit_name: str) -> bool:
    return run_command_chain([
        ['systemctl', '--user', 'enable', unit_name],
    ])


def disable_systemd_unit(unit_name: str) -> bool:
    return run_command_chain([
        ['systemctl', '--user', 'disable', unit_name],
    ])


def systemctl_is_running(unit_name: str) -> bool:
    result = subprocess.run([
        'systemctl', '--user', 'is-active', '--quiet', unit_name])
    return result.returncode == 0
