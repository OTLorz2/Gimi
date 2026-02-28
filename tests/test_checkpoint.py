"""Tests for checkpoint and resume functionality (T9)."""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime

from gimi.index.builder import Checkpoint


class TestCheckpoint:
    """Test checkpoint functionality."""

    @pytest.fixture
    def temp_checkpoint_file(self):
        """Create a temporary checkpoint file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{}')
            path = Path(f.name)
        yield path
        # Cleanup
        if path.exists():
            path.unlink()

    def test_initialization_with_defaults(self, temp_checkpoint_file):
        """Test checkpoint initializes with default values."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        assert checkpoint.get("version") == 1
        assert checkpoint.get("branches") == {}
        assert checkpoint.get("total_commits_processed") == 0
        assert checkpoint.get("failed_commits") == []
        assert checkpoint.get("in_progress") is False

    def test_set_and_get(self, temp_checkpoint_file):
        """Test setting and getting values."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        checkpoint.set("test_key", "test_value")
        assert checkpoint.get("test_key") == "test_value"

        # Test default value
        assert checkpoint.get("nonexistent", "default") == "default"

    def test_branch_state_management(self, temp_checkpoint_file):
        """Test branch-specific state management."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        # Set branch state
        checkpoint.set_branch_state("main", {
            "last_commit": "abc123",
            "commits_processed": 100,
            "status": "in_progress"
        })

        # Get branch state
        state = checkpoint.get_branch_state("main")
        assert state["last_commit"] == "abc123"
        assert state["commits_processed"] == 100
        assert state["status"] == "in_progress"

        # Get non-existent branch returns defaults
        non_existent = checkpoint.get_branch_state("feature")
        assert non_existent["status"] == "pending"

    def test_atomic_save(self, temp_checkpoint_file):
        """Test atomic save with temp file and rename."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        checkpoint.set("key1", "value1")
        checkpoint.save()

        # Verify file exists and contains data
        assert temp_checkpoint_file.exists()
        with open(temp_checkpoint_file, 'r') as f:
            data = json.load(f)
        assert data["key1"] == "value1"
        assert "last_updated" in data

    def test_in_progress_tracking(self, temp_checkpoint_file):
        """Test in_progress flag for tracking indexing status."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        assert checkpoint.get("in_progress") is False

        checkpoint.mark_in_progress(True)
        assert checkpoint.get("in_progress") is True

        checkpoint.mark_in_progress(False)
        assert checkpoint.get("in_progress") is False

    def test_failed_commits_tracking(self, temp_checkpoint_file):
        """Test tracking of failed commits."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        # Initially empty
        assert checkpoint.get_failed_commits() == []

        # Add failed commits
        checkpoint.add_failed_commit("abc123", "Network timeout")
        checkpoint.add_failed_commit("def456", "Parse error")

        failed = checkpoint.get_failed_commits()
        assert len(failed) == 2
        assert failed[0]["hash"] == "abc123"
        assert failed[0]["error"] == "Network timeout"
        assert "timestamp" in failed[0]

        # Clear failed commits
        checkpoint.clear_failed_commits()
        assert checkpoint.get_failed_commits() == []

    def test_can_resume(self, temp_checkpoint_file):
        """Test can_resume check."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        # Initially cannot resume
        assert checkpoint.can_resume() is False

        # Set up resumable state
        checkpoint.set("in_progress", True)
        checkpoint.set_branch_state("main", {
            "last_commit": "abc123",
            "status": "in_progress"
        })
        checkpoint.save()

        assert checkpoint.can_resume() is True

    def test_get_resume_branches(self, temp_checkpoint_file):
        """Test getting branches that can be resumed."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        # Initially empty
        assert checkpoint.get_resume_branches() == []

        # Set up branches
        checkpoint.set_branch_state("main", {
            "last_commit": "abc123",
            "status": "in_progress"
        })
        checkpoint.set_branch_state("feature", {
            "last_commit": "def456",
            "status": "completed"
        })
        checkpoint.set_branch_state("bugfix", {
            "last_commit": "ghi789",
            "status": "in_progress"
        })

        # Should only return branches with in_progress status
        resume_branches = checkpoint.get_resume_branches()
        assert "main" in resume_branches
        assert "bugfix" in resume_branches
        assert "feature" not in resume_branches

    def test_clear(self, temp_checkpoint_file):
        """Test clearing checkpoint."""
        checkpoint = Checkpoint(temp_checkpoint_file)

        # Add some data
        checkpoint.set("key", "value")
        checkpoint.set_branch_state("main", {"last_commit": "abc123"})
        checkpoint.save()

        assert temp_checkpoint_file.exists()

        # Clear
        checkpoint.clear()

        # Should reset to defaults
        assert checkpoint.get("version") == 1
        assert checkpoint.get("branches") == {}
        assert checkpoint.get("in_progress") is False
        assert not temp_checkpoint_file.exists()
