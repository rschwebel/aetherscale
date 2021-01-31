import enum
from pathlib import Path

from aetherscale import config


class ResourceType(enum.Enum):
    VM = enum.auto()
    VPN = enum.auto()


def user_image_path(vm_id: str) -> Path:
    return config.USER_IMAGE_FOLDER / f'{vm_id}.qcow2'


def qemu_socket_monitor(vm_id: str) -> Path:
    return Path(f'/tmp/aetherscale-qmp-{vm_id}.sock')


def qemu_socket_guest_agent(vm_id: str) -> Path:
    return Path(f'/tmp/aetherscale-qga-{vm_id}.sock')


def resource_config_path(
        resource_type: ResourceType, resource_name: str) -> Path:
    if resource_type == ResourceType.VM:
        resource_folder = 'vm'
    elif resource_type == ResourceType.VPN:
        resource_folder = 'vpn'
    else:
        raise ValueError(f'Unknown resource type {resource_type}')

    return config.AETHERSCALE_CONFIG_DIR / resource_folder / resource_name
