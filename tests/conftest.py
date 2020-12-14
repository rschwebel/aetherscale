from pathlib import Path

import pytest

from aetherscale.services import ServiceManager
import aetherscale.timing


@pytest.fixture
def tmppath(tmpdir):
    yield Path(tmpdir)


@pytest.fixture
def timeout():
    return aetherscale.timing.timeout


@pytest.fixture
def mock_service_manager():
    class MockServiceManager(ServiceManager):
        def __init__(self):
            self.services = set()
            self.started_services = set()
            self.enabled_services = set()

        def install_service(self, config_file: Path, service_name: str) -> bool:
            self.services.add(service_name)
            return True

        def uninstall_service(self, service_name: str) -> bool:
            try:
                self.services.remove(service_name)
            except KeyError:
                # should not fail if was already uninstalled
                pass

            return True

        def start_service(self, service_name: str) -> bool:
            self.started_services.add(service_name)
            return True

        def stop_service(self, service_name: str) -> bool:
            try:
                self.started_services.remove(service_name)
            except KeyError:
                # should not fail if was already stopped
                pass

            return True

        def enable_service(self, service_name: str) -> bool:
            self.enabled_services.add(service_name)
            return True

        def disable_service(self, service_name: str) -> bool:
            try:
                self.enabled_services.remove(service_name)
            except KeyError:
                # should not fail if was already disabled
                pass

            return True

        def service_is_running(self, service_name: str) -> bool:
            return service_name in self.started_services

        def service_exists(self, service_name: str) -> bool:
            return service_name in self.services

    return MockServiceManager()
