#!/usr/bin/env python

import sys
import time
from typing import List

from aetherscale.client import ServerCommunication


def create_rabbitmq_vm(comm: ServerCommunication) -> str:
    responses = comm.send_msg({
        'command': 'create-vm',
        'options': {
            # The rabbitmq image has to be created before running this script
            'image': 'rabbitmq',
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


def is_external_ip(ip: str) -> bool:
    """Quick hack to check whether an IP returned by list-vms is an
    external IP address"""
    if ':' in ip:
        first_part = ip.split(':')[0]

        try:
            if int('fe80', 16) <= int(first_part, 16) <= int('febf', 16):
                # link-local
                return False
        except ValueError:
            # if it cannot be parsed as hex, it's not in range
            return False

    if ip == '::1' or ip == '127.0.0.1':
        # localhost
        return False

    return True


def format_ip_for_url(ip: str) -> str:
    if ':' in ip:
        return f'[{ip}]'
    else:
        return ip


def main():
    with ServerCommunication() as comm:
        try:
            vm_id = create_rabbitmq_vm(comm)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

    time.sleep(30)
    # TODO: There seems to be a bug in ServerCommunication so that we can only
    # exchange one message pair per context
    # Probably related to the AMQ reply-to channel
    with ServerCommunication() as comm:
        ips = get_vm_ips(vm_id, comm)

    ips = [f'http://{format_ip_for_url(ip)}:15672/' for ip in ips
           if is_external_ip(ip)]

    print(ips)


if __name__ == '__main__':
    main()
