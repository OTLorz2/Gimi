"""File locking utilities for .gimi directory operations."""

import os
import time
import atexit
from pathlib import Path
from typing import Optional


class LockError(Exception):
    """Raised when lock operations fail."""
    pass


class GimiLock:
    """
    File-based lock for .gimi directory write operations.

    Uses a PID file in .gimi/lock to coordinate between processes.
    Only one process can hold the write lock at a time.
    """

    LOCK_FILENAME = "lock"
    LOCK_POLL_INTERVAL = 0.1  # seconds
    LOCK_ACQUIRE_TIMEOUT = 30  # seconds

    def __init__(self, gimi_dir: Path):
        """
        Initialize lock manager.

        Args:
            gimi_dir: Path to .gimi directory
        """
        self.gimi_dir = gimi_dir
        self.lock_file = gimi_dir / self.LOCK_FILENAME
        self._owned = False
        self._pid = os.getpid()

    def _read_lock_pid(self) -> Optional[int]:
        """Read PID from lock file if it exists."""
        try:
            if self.lock_file.exists():
                content = self.lock_file.read_text().strip()
                return int(content)
        except (ValueError, IOError):
            pass
        return None

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process with given PID exists."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Try to acquire the lock.

        Args:
            blocking: If True, block until lock is available
            timeout: Maximum time to wait (None = use default)

        Returns:
            True if lock was acquired, False otherwise
        """
        if self._owned:
            return True

        timeout = timeout or self.LOCK_ACQUIRE_TIMEOUT
        start_time = time.time()

        while True:
            # Check if lock file exists
            existing_pid = self._read_lock_pid()

            if existing_pid is None:
                # No lock file, try to create one
                try:
                    self.lock_file.write_text(str(self._pid))
                    # Verify we got the lock
                    current = self._read_lock_pid()
                    if current == self._pid:
                        self._owned = True
                        atexit.register(self.release)
                        return True
                except IOError:
                    pass
            elif existing_pid == self._pid:
                # We already own the lock
                self._owned = True
                return True
            elif not self._is_process_alive(existing_pid):
                # Stale lock from dead process, try to break it
                try:
                    self.lock_file.unlink()
                    continue  # Try again
                except IOError:
                    pass

            if not blocking:
                return False

            # Check timeout
            if time.time() - start_time > timeout:
                return False

            # Wait a bit before retrying
            time.sleep(self.LOCK_POLL_INTERVAL)

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> None:
        """
        Acquire the lock or raise LockError.

        Args:
            blocking: If True, block until lock is available
            timeout: Maximum time to wait

        Raises:
            LockError: If lock cannot be acquired
        """
        if not self._acquire(blocking, timeout):
            existing_pid = self._read_lock_pid()
            raise LockError(
                f"Could not acquire lock on {self.gimi_dir}. "
                f"Another process (PID: {existing_pid}) may be holding it. "
                f"Try again later or remove stale lock file: {self.lock_file}"
            )

    def release(self) -> None:
        """Release the lock if owned."""
        if not self._owned:
            return

        try:
            existing = self._read_lock_pid()
            if existing == self._pid:
                self.lock_file.unlink(missing_ok=True)
        except IOError:
            pass
        finally:
            self._owned = False
            # Unregister from atexit if possible
            try:
                atexit.unregister(self.release)
            except (ValueError, AttributeError):
                pass

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False


def with_lock(gimi_dir: Path, blocking: bool = True, timeout: Optional[float] = None):
    """
    Decorator/context manager for locking operations.

    Args:
        gimi_dir: Path to .gimi directory
        blocking: Whether to block waiting for lock
        timeout: Maximum wait time

    Returns:
        Context manager that yields GimiLock instance

    Example:
        with with_lock(gimi_dir) as lock:
            # Do locked operations
            pass
    """
    lock = GimiLock(gimi_dir)
    lock.acquire(blocking, timeout)
    try:
        yield lock
    finally:
        lock.release()
