from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess

from aetherscale.execution import run_command_chain


class ServiceManager(ABC):
    @abstractmethod
    def install_service(self, config_file: Path, service_name: str) -> bool:
        """Installs a service on the system for possible activation"""

    @abstractmethod
    def uninstall_service(self, service_name: str) -> bool:
        """Removes a service from the system once it's no longer needed"""

    @abstractmethod
    def start_service(self, service_name: str) -> bool:
        """Start a service"""

    @abstractmethod
    def stop_service(self, service_name: str) -> bool:
        """Stop a service"""

    @abstractmethod
    def enable_service(self, service_name: str) -> bool:
        """Enable a service so that it will be auto-started on reboots"""

    @abstractmethod
    def disable_service(self, service_name: str) -> bool:
        """Remove a service from autostart"""

    @abstractmethod
    def service_is_running(self, service_name: str) -> bool:
        """Check whether a service is currently running"""

    @abstractmethod
    def service_exists(self, service_name: str) -> bool:
        """Check whether a service is currently installed"""


class SystemdServiceManager(ServiceManager):
    def __init__(self, unit_folder: Path):
        self.unit_folder = unit_folder

    def install_service(self, config_file: Path, service_name: str) -> bool:
        if '.' not in service_name:
            raise ValueError('Unit name must contain the suffix, e.g. .service')

        target_unit_path = self._systemd_unit_path(service_name)
        target_unit_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copyfile(config_file, target_unit_path)
        except OSError:
            return False

        # Reload system
        r = subprocess.run(['systemctl', '--user', 'daemon-reload'])
        return r.returncode == 0

    def uninstall_service(self, service_name: str) -> bool:
        if '.' not in service_name:
            raise ValueError('Unit name must contain the suffix, e.g. .service')

        try:
            self._systemd_unit_path(service_name).unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def start_service(self, service_name: str) -> bool:
        return run_command_chain([
            ['systemctl', '--user', 'start', service_name],
        ])

    def stop_service(self, service_name: str) -> bool:
        return run_command_chain([
            ['systemctl', '--user', 'stop', service_name],
        ])

    def enable_service(self, service_name: str) -> bool:
        return run_command_chain([
            ['systemctl', '--user', 'enable', service_name],
        ])

    def disable_service(self, service_name: str) -> bool:
        return run_command_chain([
            ['systemctl', '--user', 'disable', service_name],
        ])

    def service_is_running(self, service_name: str) -> bool:
        result = subprocess.run([
            'systemctl', '--user', 'is-active', '--quiet', service_name])
        return result.returncode == 0

    def service_exists(self, service_name: str) -> bool:
        return self._systemd_unit_path(service_name).is_file()

    def _systemd_unit_path(self, service_name: str) -> Path:
        return self.unit_folder / service_name
