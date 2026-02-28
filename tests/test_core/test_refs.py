"""
Tests for refs snapshot handling (T4).
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gimi.core.refs import (
    load_refs_snapshot,
    save_refs_snapshot,
    get_current_refs,
    compare_refs,
    RefsError
)


class TestLoadRefsSnapshot:
    """Tests for loading refs snapshot."""

    def test_load_existing_snapshot(self, gimi_dir, sample_refs_snapshot):
        """Test loading an existing refs snapshot."""
        snapshot_path = gimi_dir / "refs_snapshot.json"
        snapshot_path.write_text(json.dumps(sample_refs_snapshot))

        result = load_refs_snapshot(gimi_dir)

        assert result == sample_refs_snapshot

    def test_load_nonexistent_snapshot(self, gimi_dir):
        """Test loading non-existent snapshot returns empty dict."""
        result = load_refs_snapshot(gimi_dir)

        assert result == {}

    def test_load_invalid_json(self, gimi_dir):
        """Test loading invalid JSON raises error."""
        snapshot_path = gimi_dir / "refs_snapshot.json"
        snapshot_path.write_text("invalid json")

        with pytest.raises(RefsError) as exc_info:
            load_refs_snapshot(gimi_dir)

        assert "Invalid JSON" in str(exc_info.value)


class TestSaveRefsSnapshot:
    """Tests for saving refs snapshot."""

    def test_save_snapshot_creates_file(self, gimi_dir, sample_refs_snapshot):
        """Test saving snapshot creates file."""
        save_refs_snapshot(gimi_dir, sample_refs_snapshot)

        snapshot_path = gimi_dir / "refs_snapshot.json"
        assert snapshot_path.exists()

        saved = json.loads(snapshot_path.read_text())
        assert saved == sample_refs_snapshot

    def test_save_snapshot_overwrites_existing(self, gimi_dir):
        """Test saving snapshot overwrites existing."""
        snapshot_path = gimi_dir / "refs_snapshot.json"
        snapshot_path.write_text(json.dumps({"old": "refs"}))

        new_snapshot = {"new": "refs"}
        save_refs_snapshot(gimi_dir, new_snapshot)

        saved = json.loads(snapshot_path.read_text())
        assert saved == new_snapshot

    def test_save_snapshot_pretty_print(self, gimi_dir, sample_refs_snapshot):
        """Test that snapshot is pretty-printed."""
        save_refs_snapshot(gimi_dir, sample_refs_snapshot)

        snapshot_path = gimi_dir / "refs_snapshot.json"
        content = snapshot_path.read_text()

        # Should have indentation
        assert '\n' in content


class TestGetCurrentRefs:
    """Tests for getting current refs from git."""

    def test_get_current_refs_success(self, temp_dir):
        """Test successfully getting current refs."""
        expected_refs = {
            "main": "abc123def456",
            "develop": "def789abc012"
        }

        with patch('gimi.core.refs.run_git_command') as mock_run:
            mock_run.return_value = [
                "abc123def456 refs/heads/main",
                "def789abc012 refs/heads/develop"
            ]

            result = get_current_refs(temp_dir)

            assert result == expected_refs

    def test_get_current_refs_empty(self, temp_dir):
        """Test getting refs when no branches exist."""
        with patch('gimi.core.refs.run_git_command') as mock_run:
            mock_run.return_value = []

            result = get_current_refs(temp_dir)

            assert result == {}

    def test_get_current_refs_git_error(self, temp_dir):
        """Test handling of git command errors."""
        with patch('gimi.core.refs.run_git_command') as mock_run:
            mock_run.side_effect = Exception("Git command failed")

            with pytest.raises(RefsError) as exc_info:
                get_current_refs(temp_dir)

            assert "Failed to get current refs" in str(exc_info.value)


class TestCompareRefs:
    """Tests for comparing refs snapshots."""

    def test_compare_identical_refs(self):
        """Test comparing identical refs."""
        old_refs = {"main": "abc123", "develop": "def456"}
        new_refs = {"main": "abc123", "develop": "def456"}

        result = compare_refs(old_refs, new_refs)

        assert result["changed"] is False
        assert result["added"] == []
        assert result["removed"] == []
        assert result["modified"] == []

    def test_compare_added_refs(self):
        """Test detecting added refs."""
        old_refs = {"main": "abc123"}
        new_refs = {"main": "abc123", "develop": "def456"}

        result = compare_refs(old_refs, new_refs)

        assert result["changed"] is True
        assert result["added"] == ["develop"]
        assert result["removed"] == []

    def test_compare_removed_refs(self):
        """Test detecting removed refs."""
        old_refs = {"main": "abc123", "develop": "def456"}
        new_refs = {"main": "abc123"}

        result = compare_refs(old_refs, new_refs)

        assert result["changed"] is True
        assert result["added"] == []
        assert result["removed"] == ["develop"]

    def test_compare_modified_refs(self):
        """Test detecting modified refs."""
        old_refs = {"main": "abc123", "develop": "def456"}
        new_refs = {"main": "xyz789", "develop": "def456"}

        result = compare_refs(old_refs, new_refs)

        assert result["changed"] is True
        assert result["modified"] == ["main"]

    def test_compare_empty_refs(self):
        """Test comparing empty refs."""
        old_refs = {}
        new_refs = {}

        result = compare_refs(old_refs, new_refs)

        assert result["changed"] is False
