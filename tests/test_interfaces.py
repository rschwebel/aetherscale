from aetherscale.interfaces import create_mac_address


def test_mac_address_is_random():
    mac_a = create_mac_address()
    mac_b = create_mac_address()

    assert mac_a != mac_b
