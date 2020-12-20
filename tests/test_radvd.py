import os
import pytest
import stat

from aetherscale.vpn import radvd


def test_add_interface_config(tmppath):
    r = radvd.Radvd(tmppath / 'radvd.conf', '2001:0db8:0')
    r.add_interface('my-interface', '2001:0db8:0::/64')
    r.add_interface('my-second-interface', '2001:0db8:1::/64')

    with open(r.config_file) as f:
        content = f.read()

    assert 'my-interface' in content
    assert '001:0db8::/64'
    assert 'my-second-interface' in content


def test_cannot_assign_same_prefix_twice(tmppath):
    r = radvd.Radvd(tmppath / 'radvd.conf', '2001:0db8:0')
    r.add_interface('first', '2001:0db8::/64')

    with pytest.raises(radvd.RadvdException):
        r.add_interface('second', '2001:0db8::/64')


def test_generate_next_prefix(tmppath):
    r = radvd.Radvd(tmppath / 'radvd.conf', prefix='2001:0db8:0')
    prefix = r.generate_prefix()
    r.add_interface('interface', prefix)
    prefix2 = r.generate_prefix()

    assert prefix != prefix2


def test_config_is_readonly(tmppath):
    r = radvd.Radvd(tmppath / 'radvd.conf', '2001:0db8:0')
    r.add_interface('some-interface', '::/64')

    assert stat.S_IMODE(os.lstat(r.config_file).st_mode) == 0o400


def test_drops_privileges(tmppath):
    r = radvd.Radvd(tmppath / 'radvd.conf', '2001:0db8:0')
    assert '-u' in r.get_start_command()
