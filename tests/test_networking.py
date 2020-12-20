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
