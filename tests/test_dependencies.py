from aetherscale.dependencies \
    import find_missing_dependencies, build_dependency_help_text


def test_existing_binary():
    missing = find_missing_dependencies(['sh'])
    assert len(missing) == 0


def test_missing_binary():
    missing = find_missing_dependencies(['9c4f52e32803b906214f6059a8e2850f'])
    assert len(missing) == 1


def test_build_help():
    help_text = build_dependency_help_text(['systemctl'])
    assert help_text != ''


def test_unknown_missing_dependency():
    """if the dependency is not known, it should still be listed with a generic
    help text"""

    missing_command = '9c4f52e32803b906214f6059a8e2850f'
    help_text = build_dependency_help_text([missing_command])
    assert missing_command in help_text
