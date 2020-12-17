#!/usr/bin/env python

import jinja2
from pathlib import Path
import sys
import tempfile

from aetherscale.client import ServerCommunication


def create_vm(init_script: Path, comm: ServerCommunication) -> str:
    with open(init_script) as f:
        script = f.read()

    responses = comm.send_msg({
        'command': 'create-vm',
        'options': {
            'image': 'ubuntu-20.04.1-server-amd64',
            'init-script': script,
        }
    }, response_expected=True)

    if len(responses) != 1:
        raise RuntimeError(
            'Did not receive exactly one response, something went wrong')

    if responses[0]['execution-info']['status'] != 'success':
        raise RuntimeError('Execution was not successful')

    return responses[0]['response']['vm-id']


def main():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
    template = env.get_template('jitsi-install.sh.jinja2')

    with tempfile.NamedTemporaryFile('wt') as f:
        template.stream(hostname='jitsi.example.com').dump(f.name)

        with ServerCommunication() as comm:
            try:
                vm_id = create_vm(Path(f.name), comm)
                print(vm_id)
            except RuntimeError as e:
                print(str(e), file=sys.stderr)
                sys.exit(1)


if __name__ == '__main__':
    main()
