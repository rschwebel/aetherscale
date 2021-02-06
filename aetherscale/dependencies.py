import shutil
from typing import List


BINARY_DEPENDENCIES = {
    'systemctl':
        'systemd is required by aetherscale. For support of other '
        'service managers a new ServiceManager subclass is required. '
        'Feel free to open an issue at Github.',
    'guestmount':
        'libguestfs is required by aetherscale. You can install it:\n\n'
        '    On Ubuntu: apt install libguestfs-tools\n'
        '    On Arch Linux: pacman -S libguestfs',
    'qemu-img':
        'QEMU is required by aetherscale. You can install it:\n\n'
        '    On Ubuntu: apt install qemu-utils qemu-kvm\n'
        '    On Arch Linux: pacman -S qemu-headless',
}


def find_missing_dependencies(dependency_commands: List[str]) -> List[str]:
    return [cmd for cmd in dependency_commands if not shutil.which(cmd)]


def build_dependency_help_text(missing_dependencies: List[str]) -> str:
    full_help = []
    for dependency in missing_dependencies:
        try:
            full_help.append(BINARY_DEPENDENCIES[dependency])
        except KeyError:
            full_help.append(f'{dependency} is required by aetherscale.')

    return '\n\n'.join(full_help)
