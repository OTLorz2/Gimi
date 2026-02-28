"""
File locking implementation for .gimi directory operations (T2).

This module provides process-level locking for .gimi operations
to prevent concurrent writes that could corrupt the index.
"""
import os
import time
from pathlib import Path
from typing import Optional, Union


class LockError(Exception):
    """Error related to lock operations."""
    pass


class LockTimeoutError(LockError):
    """Error raised when lock acquisition times out."""
    pass


class FileLock:
    """
    A file-based lock using PID files.

    This implementation creates a lock file containing the process PID.
    The lock is considered valid if:
    1. The lock file exists
    2. The PID in the file corresponds to a running process

    Stale locks (where the owning process no longer exists) are
    automatically cleaned up.
    """

    def __init__(self, lock_path: Union[str, Path]):
        """
        Initialize the file lock.

        Args:
            lock_path: Path to the lock file.
        """
        self.lock_path = Path(lock_path)
        self._owned = False

    def acquire(
        self,
        blocking: bool = True,
        timeout: Optional[float] = None
    ) -> bool:
        """
        Acquire the lock.

        Args:
            blocking: If True, block until lock is acquired.
            If False, return immediately if lock cannot be acquired.
            timeout: Maximum time to wait for lock (in seconds).
            Only used if blocking is True.

        Returns:
            True if lock was acquired, False if not (only in non-blocking mode).

        Raises:
            LockError: If lock is already held by another process and
            blocking is False.
            LockTimeoutError: If timeout is reached while waiting for lock.
        """
        start_time = time.time()

        while True:
            # Check if we already own this lock
            if self._is_owned_by_us():
                self._owned = True
                return True

            # Check if lock is held by another process
            if self._is_locked():
                if not blocking:
                    raise LockError(
                        f"Lock is already held by another process: {self.lock_path}"
                    )

                # Check timeout
                if timeout is not None and (time.time() - start_time) >= timeout:
                    raise LockTimeoutError(
                        f"Timeout waiting for lock: {self.lock_path}"
                    )

                # Wait a bit before retrying
                time.sleep(0.1)
                continue

            # Try to acquire the lock
            try:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                self.lock_path.write_text(str(os.getpid()))
                self._owned = True
                return True
            except Exception as e:
                raise LockError(f"Failed to acquire lock: {e}")

    def release(self) -> None:
        """
        Release the lock.

        Raises:
            LockError: If lock is not owned by this process.
        """
        if not self._owned:
            # Check if we own the lock
            if not self._is_owned_by_us():
                raise LockError(
                    "Cannot release lock: not owned by this process"
                )

        try:
            if self.lock_path.exists():
                self.lock_path.unlink()
            self._owned = False
        except Exception as e:
            raise LockError(f"Failed to release lock: {e}")

    def is_locked(self) -> bool:
        """
        Check if the lock is currently held (by any process).

        Returns:
            True if lock is held, False otherwise.
        """
        return self._is_locked()

    def _is_locked(self) -> bool:
        """Internal method to check if lock is held."""
        if not self.lock_path.exists():
            return False

        try:
            pid = int(self.lock_path.read_text().strip())
            # Check if process is still running
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                # Process doesn't exist, clean up stale lock
                try:
                    self.lock_path.unlink()
                except:
                    pass
                return False
        except (ValueError, IOError):
            # Invalid lock file content
            return False

    def _is_owned_by_us(self) -> bool:
        """Check if this process owns the lock."""
        if not self.lock_path.exists():
            return False

        try:
            pid = int(self.lock_path.read_text().strip())
            return pid == os.getpid()
        except (ValueError, IOError):
            return False

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False


class GimiLock:
    """
    A simple lock manager for the .gimi directory.

    This is a higher-level wrapper around FileLock for the Gimi use case.
    """

    def __init__(self, gimi_dir: Union[str, Path]):
        """
        Initialize the Gimi lock.

        Args:
            gimi_dir: Path to the .gimi directory.
        """
        self.gimi_dir = Path(gimi_dir)
        self.lock_file = self.gimi_dir / "lock"
        self._file_lock = FileLock(self.lock_file)
        self._owned = False

    def _acquire(self, blocking: bool = True) -> bool:
        """
        Internal acquire method for compatibility with tests.

        Args:
            blocking: If True, block until lock is acquired.

        Returns:
            True if lock was acquired.
        """
        return self.acquire(blocking=blocking)

    def acquire(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquire the lock.

        Args:
            blocking: If True, block until lock is acquired.
            timeout: Maximum time to wait (only if blocking is True).

        Returns:
            True if lock was acquired.
        """
        result = self._file_lock.acquire(blocking=blocking, timeout=timeout)
        if result:
            self._owned = True
        return result

    def release(self) -> None:
        """Release the lock."""
        self._file_lock.release()
        self._owned = False

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
        return False


# Context manager for lock
def with_lock(gimi_dir: Union[str, Path]):
    """
    Context manager for acquiring a lock on the .gimi directory.

    Args:
        gimi_dir: Path to the .gimi directory.

    Yields:
        GimiLock: The acquired lock.

    Example:
        with with_lock(gimi_dir) as lock:
            # Do something with the lock held
            pass
    """
    lock = GimiLock(gimi_dir)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()


# Convenience functions for simple lock operations
def acquire_lock(
    lock_path: Union[str, Path],
    blocking: bool = True,
    timeout: Optional[float] = None
) -> bool:
    """
    Acquire a file lock.

    Args:
        lock_path: Path to the lock file.
        blocking: If True, block until lock is acquired.
        timeout: Maximum time to wait (only if blocking is True).

    Returns:
        True if lock was acquired.

    Raises:
        LockError: If lock cannot be acquired.
        LockTimeoutError: If timeout is reached.
    """
    lock = FileLock(lock_path)
    return lock.acquire(blocking=blocking, timeout=timeout)


def release_lock(lock_path: Union[str, Path]) -> None:
    """
    Release a file lock.

    Args:
        lock_path: Path to the lock file.

    Raises:
        LockError: If lock cannot be released.
    """
    lock = FileLock(lock_path)
    lock.release()


def is_locked(lock_path: Union[str, Path]) -> bool:
    """
    Check if a lock is currently held.

    Args:
        lock_path: Path to the lock file.

    Returns:
        True if lock is held, False otherwise.
    """
    lock = FileLock(lock_path)
    return lock.is_locked()
