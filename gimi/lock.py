"""
T2: Write path locking implementation.

This module provides file locking mechanisms for the .gimi directory
to prevent concurrent writes from multiple gimi processes.

Uses a PID file approach for cross-platform compatibility.
"""

import os
import atexit
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


class LockError(Exception):
    """Base exception for lock-related errors."""
    pass


class LockAcquisitionError(LockError):
    """Raised when lock cannot be acquired."""
    pass


class LockHeldByOtherProcess(LockAcquisitionError):
    """Raised when lock is held by another process."""
    pass


@dataclass
class LockInfo:
    """Information about a held lock."""
    pid: int
    timestamp: float
    hostname: Optional[str] = None


class FileLock:
    """
    File-based lock using PID file mechanism.

    This lock is:
    - Cross-platform (Windows, Linux, macOS)
    - Process-safe (uses PID to detect stale locks)
    - Automatic cleanup on process exit

    Usage:
        lock = FileLock("/path/to/lockfile")
        with lock:
            # Critical section
            pass
    """

    def __init__(
        self,
        lock_file: Path,
        timeout: float = 0.0,
        check_interval: float = 0.1,
        stale_check: bool = True
    ):
        """
        Initialize the file lock.

        Args:
            lock_file: Path to the lock file (PID file)
            timeout: Maximum time to wait for lock (0 = no wait, fail immediately)
            check_interval: How often to check for lock availability
            stale_check: Whether to check for and remove stale locks
        """
        self.lock_file = Path(lock_file)
        self.timeout = timeout
        self.check_interval = check_interval
        self.stale_check = stale_check
        self._owned = False

    def _read_lock_info(self) -> Optional[LockInfo]:
        """Read lock information from the lock file."""
        try:
            if not self.lock_file.exists():
                return None
            content = self.lock_file.read_text().strip()
            if not content:
                return None

            parts = content.split(',')
            pid = int(parts[0])
            timestamp = float(parts[1]) if len(parts) > 1 else 0.0
            hostname = parts[2] if len(parts) > 2 else None

            return LockInfo(pid=pid, timestamp=timestamp, hostname=hostname)
        except (ValueError, OSError):
            return None

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process with given PID is still running."""
        try:
            if os.name == 'nt':  # Windows
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:  # Unix-like
                os.kill(pid, 0)
                return True
        except (OSError, ImportError, AttributeError):
            return False

    def _remove_stale_lock(self) -> bool:
        """Remove a stale lock if the owning process is dead."""
        if not self.stale_check:
            return False

        lock_info = self._read_lock_info()
        if lock_info is None:
            return True  # No lock to check

        # Check if process is alive
        if not self._is_process_alive(lock_info.pid):
            try:
                self.lock_file.unlink(missing_ok=True)
                return True
            except OSError:
                return False

        return False

    def _write_lock(self) -> None:
        """Write the lock file with current process info."""
        import socket
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        hostname = socket.gethostname()
        content = f"{os.getpid()},{time.time()},{hostname}"
        self.lock_file.write_text(content)

    def acquire(self) -> bool:
        """
        Acquire the lock.

        Returns:
            True if lock was acquired, False otherwise.

        Raises:
            LockHeldByOtherProcess: If lock is held by another live process.
        """
        if self._owned:
            return True

        start_time = time.time()

        while True:
            # Try to remove stale lock
            if self.lock_file.exists():
                if self._remove_stale_lock():
                    pass  # Stale lock removed, can try to acquire
                else:
                    # Lock is held by another live process
                    if self.timeout == 0:
                        lock_info = self._read_lock_info()
                        pid = lock_info.pid if lock_info else "unknown"
                        raise LockHeldByOtherProcess(
                            f"Lock is held by another process (PID: {pid}). "
                            "Use --wait or ensure no other gimi process is running."
                        )

                    elapsed = time.time() - start_time
                    if elapsed >= self.timeout:
                        raise LockAcquisitionError(
                            f"Could not acquire lock within {self.timeout}s timeout"
                        )

                    time.sleep(self.check_interval)
                    continue

            # Try to acquire lock
            try:
                self._write_lock()
                self._owned = True
                atexit.register(self.release)
                return True
            except OSError as e:
                raise LockAcquisitionError(f"Failed to create lock file: {e}")

    def release(self) -> None:
        """Release the lock."""
        if not self._owned:
            return

        try:
            if self.lock_file.exists():
                # Verify we own this lock
                lock_info = self._read_lock_info()
                if lock_info and lock_info.pid == os.getpid():
                    self.lock_file.unlink(missing_ok=True)
        except OSError:
            pass  # Best effort
        finally:
            self._owned = False
            try:
                atexit.unregister(self.release)
            except Exception:
                pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class GimiLockManager:
    """
    Manages locks for the .gimi directory.

    Provides separate locks for:
    - index writes
    - vector writes
    - cache writes
    """

    def __init__(self, gimi_dir: Path):
        self.gimi_dir = Path(gimi_dir)
        self.locks_dir = self.gimi_dir / '.locks'
        self.locks_dir.mkdir(parents=True, exist_ok=True)

        # Define lock files for different operations
        self._index_lock = FileLock(self.locks_dir / 'index.lock')
        self._vector_lock = FileLock(self.locks_dir / 'vectors.lock')
        self._cache_lock = FileLock(self.locks_dir / 'cache.lock')
        self._global_lock = FileLock(self.locks_dir / 'global.lock')

    @property
    def index(self) -> FileLock:
        """Lock for index writes."""
        return self._index_lock

    @property
    def vectors(self) -> FileLock:
        """Lock for vector writes."""
        return self._vector_lock

    @property
    def cache(self) -> FileLock:
        """Lock for cache writes."""
        return self._cache_lock

    @property
    def global_lock(self) -> FileLock:
        """Global lock for major operations."""
        return self._global_lock


def acquire_all(*locks: FileLock, timeout: float = 0.0) -> bool:
    """
    Acquire multiple locks in order to prevent deadlocks.

    Args:
        *locks: FileLock instances to acquire
        timeout: Timeout for each lock acquisition

    Returns:
        True if all locks acquired, False otherwise

    Raises:
        LockAcquisitionError: If any lock cannot be acquired
    """
    acquired = []
    try:
        for lock in locks:
            lock.timeout = timeout
            lock.acquire()
            acquired.append(lock)
        return True
    except LockError:
        # Release all acquired locks in reverse order
        for lock in reversed(acquired):
            lock.release()
        raise


if __name__ == '__main__':
    # Test the locking mechanism
    import tempfile
    import threading
    import time

    def test_basic_lock():
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / 'test.lock'
            lock = FileLock(lock_path)

            # Test acquire and release
            assert lock.acquire()
            assert lock._owned
            lock.release()
            assert not lock._owned
            print("✓ Basic lock/unlock works")

    def test_context_manager():
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / 'test.lock'
            lock = FileLock(lock_path)

            with lock:
                assert lock._owned
            assert not lock._owned
            print("✓ Context manager works")

    def test_concurrent_access():
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / 'test.lock'
            results = []

            def try_lock(timeout=0):
                lock = FileLock(lock_path, timeout=timeout)
                try:
                    lock.acquire()
                    results.append(('acquired', timeout))
                    time.sleep(0.1)
                    lock.release()
                except LockHeldByOtherProcess:
                    results.append(('blocked', timeout))

            # First thread acquires lock
            t1 = threading.Thread(target=try_lock, args=(0,))
            t1.start()
            time.sleep(0.05)  # Ensure t1 gets the lock

            # Second thread tries with no timeout (should fail immediately)
            t2 = threading.Thread(target=try_lock, args=(0,))
            t2.start()

            t1.join()
            t2.join()

            assert ('acquired', 0) in results
            assert ('blocked', 0) in results
            print("✓ Concurrent access protection works")

    test_basic_lock()
    test_context_manager()
    test_concurrent_access()
    print("\nAll lock tests passed!")
