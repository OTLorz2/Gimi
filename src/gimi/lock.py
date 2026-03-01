"""T2: File lock for .gimi writes to prevent concurrent index/cache corruption."""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

LOCK_FILENAME = ".write_lock"
LOCK_POLL_SEC = 0.5
LOCK_TIMEOUT_SEC = 300  # 5 min max wait


def _is_process_running(pid: int) -> bool:
    """Return True if a process with the given PID exists."""
    if sys.platform == "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return False


def _try_acquire(lock_path: Path) -> bool:
    """Try to create lock file exclusively; return True if we got it."""
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False


def _read_stale_pid(lock_path: Path) -> Optional[int]:
    """If lock file exists, read PID and return it if process is dead; else None."""
    try:
        raw = lock_path.read_text().strip()
        pid = int(raw)
        if _is_process_running(pid):
            return None
        return pid
    except (ValueError, OSError):
        return -1


def acquire_lock(gimi_dir: Path, wait: bool = False, timeout_sec: float = LOCK_TIMEOUT_SEC) -> bool:
    """
    Acquire the write lock under gimi_dir.
    If wait is False: return True if acquired, False if another process holds it.
    If wait is True: block until acquired or timeout; return True if acquired.
    """
    lock_path = gimi_dir / LOCK_FILENAME
    deadline = time.monotonic() + timeout_sec if wait else 0

    while True:
        if _try_acquire(lock_path):
            return True
        stale = _read_stale_pid(lock_path)
        if stale is not None:
            try:
                lock_path.unlink()
            except OSError:
                pass
            continue
        if not wait or time.monotonic() >= deadline:
            return False
        time.sleep(LOCK_POLL_SEC)


def release_lock(gimi_dir: Path) -> None:
    """Release the write lock (remove lock file). Call from same process that acquired."""
    lock_path = gimi_dir / LOCK_FILENAME
    try:
        lock_path.unlink()
    except OSError:
        pass


@contextmanager
def write_lock(gimi_dir: Path, wait: bool = True, timeout_sec: float = LOCK_TIMEOUT_SEC) -> Iterator[None]:
    """
    Context manager: acquire write lock for .gimi, yield, then release.
    Raises RuntimeError if lock could not be acquired (when wait=False or timeout when wait=True).
    """
    if not acquire_lock(gimi_dir, wait=wait, timeout_sec=timeout_sec):
        raise RuntimeError(
            "Another gimi process is writing to this repository's index. "
            "Wait for it to finish or kill that process."
        )
    try:
        yield
    finally:
        release_lock(gimi_dir)
