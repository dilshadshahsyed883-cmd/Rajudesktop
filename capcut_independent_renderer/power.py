"""Hold Windows system sleep only while this render worker is running."""
from contextlib import contextmanager
import os


@contextmanager
def keep_awake():
    held=False
    kernel=None
    if os.name=='nt':
        import ctypes
        kernel=ctypes.windll.kernel32
        held=bool(kernel.SetThreadExecutionState(0x80000001))
    try:
        yield held
    finally:
        if held and kernel:
            kernel.SetThreadExecutionState(0x80000000)
