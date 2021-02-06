import sys

from aetherscale import __version__
from aetherscale import dependencies
from aetherscale import networking
import aetherscale.api.broker
import aetherscale.api.rest


def main():
    print(f'Executing aetherscale version {__version__}.')

    missing_deps = dependencies.find_missing_dependencies(
        dependencies.BINARY_DEPENDENCIES.keys())

    if len(missing_deps) > 0:
        help_text = dependencies.build_dependency_help_text(missing_deps)
        print(help_text, file=sys.stderr)
        sys.exit(1)

    if not networking.Iproute2Network.check_device_existence('br0'):
        print('aetherscale expects a device br0 to exist', file=sys.stderr)
        sys.exit(1)

    elif len(sys.argv) >= 2 and sys.argv[1] == 'http':
        aetherscale.api.rest.app.run()
    else:
        aetherscale.api.broker.run()
