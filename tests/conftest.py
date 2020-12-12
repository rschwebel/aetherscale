from contextlib import contextmanager
import pytest
import signal


@pytest.fixture
def timeout():
    """Run a block of code with a specified timeout. If the block is not
    finished after the defined time, raise an exception."""
    def raise_exception(signum, frame):
        raise TimeoutError

    @contextmanager
    def timeout_function(seconds: int):
        try:
            signal.signal(signal.SIGALRM, raise_exception)
            signal.alarm(seconds)
            yield None
        finally:
            signal.signal(signal.SIGALRM, signal.SIG_IGN)

    return timeout_function
