from pathlib import Path
import pytest

import aetherscale.timing


@pytest.fixture
def timeout():
    return aetherscale.timing.timeout
