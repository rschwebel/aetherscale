from contextlib import contextmanager
import signal


@contextmanager
def timeout(seconds: int):
    def raise_exception(signum, frame):
        raise TimeoutError

    """Run a block of code with a specified timeout. If the block is not
    finished after the defined time, raise an exception."""
    try:
        signal.signal(signal.SIGALRM, raise_exception)
        signal.alarm(seconds)
        yield None
    finally:
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
