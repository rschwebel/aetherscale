from unittest import mock
import pytest

from aetherscale import networking


def test_mac_address_is_random():
    mac_a = networking.create_mac_address()
    mac_b = networking.create_mac_address()

    assert mac_a != mac_b


def test_device_name_validation():
    # must not raise exception
    networking.Iproute2Network.validate_device_name('valid-dev')
    networking.Iproute2Network.validate_device_name('qemu-tap-10')
    networking.Iproute2Network.validate_device_name('fifteen-chars15')

    with pytest.raises(networking.NetworkingException):
        networking.Iproute2Network.validate_device_name('too-long-device-name')

    with pytest.raises(networking.NetworkingException):
        networking.Iproute2Network.validate_device_name('invalid space')

    with pytest.raises(networking.NetworkingException):
        networking.Iproute2Network.validate_device_name('non-ascii-日本')


def test_ip_address_validation():
    # must not raise exception
    networking.Iproute2Network.validate_ip_address('10.0.0.1')
    networking.Iproute2Network.validate_ip_address('2001:0db8::3b:0:1')
    networking.Iproute2Network.validate_ip_address('10.0.0.1/32')
    networking.Iproute2Network.validate_ip_address('2001:0db8::/64')

    with pytest.raises(networking.NetworkingException):
        networking.Iproute2Network.validate_ip_address('something-invalid')


def test_iproute2_networking_scripts():
    iproute = networking.Iproute2Network()
    iproute.bridged_network('unittestbr0', 'eth0', '10.0.0.2/24', '10.0.0.1')
    iproute.tap_device('tap0', 'myuser', 'unittestbr0')
    setup_script = iproute.setup_script()
    teardown_script = iproute.teardown_script()

    assert 'link add unittestbr0 type bridge' in setup_script
    assert 'set eth0 master unittestbr0' in setup_script
    assert 'addr add 10.0.0.2/24 dev unittestbr0' in setup_script
    assert 'tuntap add dev tap0' in setup_script

    assert 'link del unittestbr0' in teardown_script
    assert 'link del tap0' in teardown_script
    assert 'addr add 10.0.0.2/24 dev eth0' in teardown_script


@mock.patch('aetherscale.execution.run_command_chain')
def test_iproute2_networking_direct_execution(command_chain):
    iproute = networking.Iproute2Network()
    iproute.bridged_network('unittestbr0', 'eth0')

    iproute.setup()

    bridge_command = ['sudo', 'ip', 'link', 'add', 'unittestbr0', 'type', 'bridge']
    assert bridge_command in command_chain.call_args[0][0]
