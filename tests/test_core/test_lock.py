"""
Tests for file locking implementation (T2).
"""
import os
import pytest
import tempfile
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

from gimi.core.lock import (
    acquire_lock,
    release_lock,
    is_locked,
    LockError,
    LockTimeoutError
)


class TestAcquireLock:
    """Tests for acquiring file locks."""

    def test_acquire_lock_creates_lock_file(self, temp_dir):
        """Test that acquiring lock creates lock file."""
        lock_path = temp_dir / "test.lock"

        acquire_lock(lock_path)

        assert lock_path.exists()

    def test_acquire_lock_writes_pid(self, temp_dir):
        """Test that lock file contains process PID."""
        lock_path = temp_dir / "test.lock"

        acquire_lock(lock_path)

        pid = int(lock_path.read_text().strip())
        assert pid == os.getpid()

    def test_acquire_lock_already_locked_same_process(self, temp_dir):
        """Test re-acquiring lock by same process is idempotent."""
        lock_path = temp_dir / "test.lock"

        acquire_lock(lock_path)
        acquire_lock(lock_path)  # Should not raise

        assert lock_path.exists()

    def test_acquire_lock_already_locked_different_process(self, temp_dir):
        """Test acquiring lock held by different process raises error."""
        lock_path = temp_dir / "test.lock"

        # Create lock file with fake PID
        lock_path.write_text("99999\n")

        # Mock os.kill to simulate process exists
        with patch('os.kill') as mock_kill:
            mock_kill.return_value = None

            with pytest.raises(LockError) as exc_info:
                acquire_lock(lock_path, blocking=False)

            assert "already held" in str(exc_info.value)

    def test_acquire_lock_with_timeout(self, temp_dir):
        """Test acquiring lock with timeout."""
        lock_path = temp_dir / "test.lock"

        # Create lock file with fake PID
        lock_path.write_text("99999\n")

        with patch('os.kill') as mock_kill:
            mock_kill.return_value = None

            with pytest.raises(LockTimeoutError):
                acquire_lock(lock_path, blocking=True, timeout=0.1)


class TestReleaseLock:
    """Tests for releasing file locks."""

    def test_release_lock_removes_file(self, temp_dir):
        """Test that releasing lock removes lock file."""
        lock_path = temp_dir / "test.lock"

        acquire_lock(lock_path)
        release_lock(lock_path)

        assert not lock_path.exists()

    def test_release_lock_not_locked(self, temp_dir):
        """Test releasing non-existent lock is safe."""
        lock_path = temp_dir / "test.lock"

        # Should not raise
        release_lock(lock_path)

    def test_release_lock_owned_by_other_process(self, temp_dir):
        """Test releasing lock owned by other process raises error."""
        lock_path = temp_dir / "test.lock"

        # Create lock file with fake PID
        lock_path.write_text("99999\n")

        with patch('os.kill') as mock_kill:
            mock_kill.return_value = None

            with pytest.raises(LockError) as exc_info:
                release_lock(lock_path)

            assert "owned by another process" in str(exc_info.value)


class TestIsLocked:
    """Tests for checking lock status."""

    def test_is_locked_true(self, temp_dir):
        """Test is_locked returns True when locked."""
        lock_path = temp_dir / "test.lock"

        acquire_lock(lock_path)

        assert is_locked(lock_path) is True

    def test_is_locked_false(self, temp_dir):
        """Test is_locked returns False when not locked."""
        lock_path = temp_dir / "test.lock"

        assert is_locked(lock_path) is False

    def test_is_locked_stale_lock(self, temp_dir):
        """Test is_locked handles stale lock files."""
        lock_path = temp_dir / "test.lock"

        # Create lock file with non-existent PID
        lock_path.write_text("99999\n")

        with patch('os.kill') as mock_kill:
            mock_kill.side_effect = ProcessLookupError()

            # Should return False and clean up stale lock
            assert is_locked(lock_path) is False
            assert not lock_path.exists()
