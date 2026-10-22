"""Cross-platform non-blocking file lock for desktop AI queue subprocesses."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import os

@contextmanager
def try_lock(location: str | Path):
    target=Path(location)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("a+b") as stream:
        if not target.stat().st_size:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        got=False
        if os.name=="nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                got=True
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                got=True
            except (BlockingIOError,OSError):
                pass
        try:
            yield got
        finally:
            if got:
                stream.seek(0)
                if os.name=="nt":
                    msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
