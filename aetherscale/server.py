import sys

from aetherscale import __version__
from aetherscale.computing import run
from aetherscale import dependencies


def main():
    print(f'Executing aetherscale version {__version__}.')

    missing_deps = dependencies.find_missing_dependencies(
        dependencies.BINARY_DEPENDENCIES.keys())

    if len(missing_deps) > 0:
        help_text = dependencies.build_dependency_help_text(missing_deps)
        print(help_text, file=sys.stderr)
    else:
        run()
