from . import __version__
from .computing import run


def main():
    print(f'Executing aetherscale version {__version__}.')

    run()
