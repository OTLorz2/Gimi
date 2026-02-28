"""
Tests for index validation (T5).
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gimi.core.validation import (
    validate_index,
    IndexValidationError,
    IndexStatus
)


class TestValidateIndex:
    """Tests for index validation."""

    def test_validate_valid_index(self, gimi_dir, sample_refs_snapshot):
        """Test validating an up-to-date index."""
        # Create refs snapshot
        snapshot_path = gimi_dir / "refs_snapshot.json"
        snapshot_path.write_text(json.dumps(sample_refs_snapshot))

        # Create index directory with some data
        index_dir = gimi_dir / "index"
        (index_dir / "commits.db").touch()

        with patch('gimi.core.validation.get_current_refs') as mock_get_refs:
            mock_get_refs.return_value = sample_refs_snapshot

            result = validate_index(gimi_dir.parent)

            assert result.status == IndexStatus.VALID
            assert result.is_valid is True
            assert result.needs_rebuild is False

    def test_validate_stale_index(self, gimi_dir, sample_refs_snapshot):
        """Test validating an out-of-date index."""
        # Create refs snapshot with old refs
        snapshot_path = gimi_dir / "refs_snapshot.json"
        snapshot_path.write_text(json.dumps(sample_refs_snapshot))

        # Create index directory
        index_dir = gimi_dir / "index"
        (index_dir / "commits.db").touch()

        # Current refs have different commit
        current_refs = dict(sample_refs_snapshot)
        current_refs["main"] = "new_commit_hash"

        with patch('gimi.core.validation.get_current_refs') as mock_get_refs:
            mock_get_refs.return_value = current_refs

            result = validate_index(gimi_dir.parent)

            assert result.status == IndexStatus.STALE
            assert result.is_valid is False
            assert result.needs_rebuild is True

    def test_validate_missing_snapshot(self, gimi_dir):
        """Test validating when refs snapshot doesn't exist."""
        # Create index directory but no snapshot
        index_dir = gimi_dir / "index"
        index_dir.mkdir(exist_ok=True)
        (index_dir / "commits.db").touch()

        result = validate_index(gimi_dir.parent)

        assert result.status == IndexStatus.MISSING_SNAPSHOT
        assert result.is_valid is False
        assert result.needs_rebuild is True

    def test_validate_missing_index(self, gimi_dir, sample_refs_snapshot):
        """Test validating when index directory doesn't exist."""
        # Create refs snapshot but no index
        snapshot_path = gimi_dir / "refs_snapshot.json"
        snapshot_path.write_text(json.dumps(sample_refs_snapshot))

        # Remove the index directory that was created by the gimi_dir fixture
        import shutil
        index_dir = gimi_dir / "index"
        if index_dir.exists():
            shutil.rmtree(index_dir)

        result = validate_index(gimi_dir.parent)

        assert result.status == IndexStatus.MISSING_INDEX
        assert result.is_valid is False
        assert result.needs_rebuild is True

    def test_validate_empty_index(self, gimi_dir, sample_refs_snapshot):
        """Test validating when index directory exists but is empty."""
        # Create refs snapshot and empty index
        snapshot_path = gimi_dir / "refs_snapshot.json"
        snapshot_path.write_text(json.dumps(sample_refs_snapshot))

        index_dir = gimi_dir / "index"
        index_dir.mkdir(exist_ok=True)

        result = validate_index(gimi_dir.parent)

        assert result.status == IndexStatus.EMPTY_INDEX
        assert result.is_valid is False
        assert result.needs_rebuild is True


class TestIndexStatus:
    """Tests for IndexStatus enum."""

    def test_valid_status(self):
        """Test VALID status properties."""
        status = IndexStatus.VALID
        assert status.is_valid is True
        assert status.needs_rebuild is False

    def test_stale_status(self):
        """Test STALE status properties."""
        status = IndexStatus.STALE
        assert status.is_valid is False
        assert status.needs_rebuild is True

    def test_missing_snapshot_status(self):
        """Test MISSING_SNAPSHOT status properties."""
        status = IndexStatus.MISSING_SNAPSHOT
        assert status.is_valid is False
        assert status.needs_rebuild is True

    def test_missing_index_status(self):
        """Test MISSING_INDEX status properties."""
        status = IndexStatus.MISSING_INDEX
        assert status.is_valid is False
        assert status.needs_rebuild is True

    def test_empty_index_status(self):
        """Test EMPTY_INDEX status properties."""
        status = IndexStatus.EMPTY_INDEX
        assert status.is_valid is False
        assert status.needs_rebuild is True
