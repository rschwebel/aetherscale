#!/usr/bin/env python

import jinja2
from pathlib import Path
import sys
import tempfile
import time
from typing import List

from aetherscale.client import ServerCommunication
import aetherscale.config
from aetherscale.timing import timeout


def create_vm(init_script: Path, comm: ServerCommunication) -> str:
    with open(init_script) as f:
        script = f.read()

    responses = comm.send_msg({
        'command': 'create-vm',
        'options': {
            'image': 'ubuntu-20.04.1-server-amd64',
            'init-script': script,
            # At the moment this is required for the installation of the
            # packages, because there is no gateway defined inside VPNs
            'public-ip': True,
            'vpn': 'jitsi',
        }
    }, response_expected=True)

    if len(responses) != 1:
        raise RuntimeError(
            'Did not receive exactly one response, something went wrong')

    if responses[0]['execution-info']['status'] != 'success':
        raise RuntimeError('Execution was not successful')

    return responses[0]['response']['vm-id']


def get_vm_ips(vm_id: str, comm: ServerCommunication) -> List[str]:
    responses = comm.send_msg({
        'command': 'list-vms',
    }, response_expected=True)

    for r in responses:
        try:
            for vm in r['response']:
                if vm['vm-id'] == vm_id:
                    return vm['ip-addresses']
        except KeyError:
            pass

    return []


def main():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader('./'))
    template = env.get_template('jitsi-install.sh.jinja2')

    with tempfile.NamedTemporaryFile('wt') as f:
        template.stream(hostname='jitsi.example.com').dump(f.name)

        with ServerCommunication() as comm:
            try:
                vm_id = create_vm(Path(f.name), comm)
            except RuntimeError as e:
                print(str(e), file=sys.stderr)
                sys.exit(1)

    try:
        # TODO: Currently, the VM image has a flaw in setup of IP addresses
        # it will wait for a DHCP to be available on all interfaces, but
        # VPN interface does not have this. To make this work with all
        # variants of vpn/public-ip we have to define fixed interface names
        # with https://www.freedesktop.org/software/systemd/man/systemd.link.html
        # and then can set the right IP lookup for each interface in
        # /etc/systemd/network/
        # or we can omit the fixed interface names and directly match on the
        # MAC address in .network files
        # (both variants have to be copied to the image before booting it)
        with timeout(300):
            ip_address = None

            while not ip_address:
                with ServerCommunication() as comm:
                    ips = get_vm_ips(vm_id, comm)
                    vpn_prefix = aetherscale.config.VPN_48_PREFIX
                    vpn_ips = [ip for ip in ips if ip.startswith(vpn_prefix)]

                    if len(vpn_ips) > 0:
                        ip_address = vpn_ips[0]

                time.sleep(5)

        print(ip_address)
    except TimeoutError:
        print('Could not retrieve IP address', file=sys.stderr)


if __name__ == '__main__':
    main()
