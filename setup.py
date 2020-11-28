import re
from setuptools import setup

version = re.search(
    r'^__version__\s*=\s*\'(.+)\'',
    open('aetherscale/__init__.py').read(),
    re.M).group(1)

with open('README.md', 'rb') as f:
    long_descr = f.read().decode('utf-8')

install_requires = [
    'pika',
    'psutil',
]

setup(
    name='aetherscale',
    packages=['aetherscale'],
    entry_points={
        'console_scripts': [
            'aetherscale=aetherscale.server:main',
            'aetherscale-cli=aetherscale.client:main',
        ],
    },
    install_requires=install_requires,
    version=version,
    description='Proof-of-concept for a small cloud computing platform',
    long_description=long_descr,
    author='Stefan Koch',
)
