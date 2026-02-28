"""Tests for incremental indexer functionality (T9)."""

import tempfile
import unittest
from pathlib import Path
from datetime import datetime

from gimi.indexer import (
    IncrementalIndexer,
    IndexingProgress,
    BatchProgress,
    IndexingState,
)
from gimi.config import LargeRepoConfig


class TestBatchProgress(unittest.TestCase):
    """Tests for BatchProgress dataclass."""

    def test_creation(self):
        """Test creating a BatchProgress."""
        batch = BatchProgress(
            batch_number=1,
            start_commit="abc123",
            end_commit="def456",
            commit_count=50,
            status="completed"
        )
        self.assertEqual(batch.batch_number, 1)
        self.assertEqual(batch.start_commit, "abc123")
        self.assertEqual(batch.status, "completed")

    def test_to_dict(self):
        """Test conversion to dictionary."""
        batch = BatchProgress(
            batch_number=1,
            start_commit="abc123",
            commit_count=50,
            status="completed"
        )
        data = batch.to_dict()
        self.assertEqual(data["batch_number"], 1)
        self.assertEqual(data["start_commit"], "abc123")

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "batch_number": 2,
            "start_commit": "xyz789",
            "end_commit": "abc123",
            "commit_count": 100,
            "started_at": "2024-01-01T00:00:00",
            "completed_at": "2024-01-01T01:00:00",
            "status": "completed"
        }
        batch = BatchProgress.from_dict(data)
        self.assertEqual(batch.batch_number, 2)
        self.assertEqual(batch.start_commit, "xyz789")
        self.assertEqual(batch.commit_count, 100)


class TestIndexingProgress(unittest.TestCase):
    """Tests for IndexingProgress dataclass."""

    def test_creation(self):
        """Test creating an IndexingProgress."""
        progress = IndexingProgress(
            state="running",
            target_branches=["main", "develop"],
            max_commits=1000,
            batch_size=100,
            total_batches=10,
            total_commits=1000,
            started_at="2024-01-01T00:00:00"
        )
        self.assertEqual(progress.state, "running")
        self.assertEqual(progress.target_branches, ["main", "develop"])
        self.assertEqual(progress.batch_size, 100)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        progress = IndexingProgress(
            state="completed",
            target_branches=["main"],
            total_commits=100,
            processed_commits=100,
            completed_at="2024-01-01T01:00:00"
        )
        data = progress.to_dict()
        self.assertEqual(data["state"], "completed")
        self.assertEqual(data["target_branches"], ["main"])
        self.assertEqual(data["total_commits"], 100)
        self.assertEqual(data["processed_commits"], 100)

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "state": "running",
            "target_branches": ["main", "feature"],
            "max_commits": 500,
            "since_date": None,
            "batch_size": 50,
            "total_batches": 10,
            "completed_batches": 3,
            "total_commits": 500,
            "processed_commits": 150,
            "batches": [],
            "started_at": "2024-01-01T00:00:00",
            "last_updated_at": "2024-01-01T00:30:00",
            "completed_at": None
        }
        progress = IndexingProgress.from_dict(data)
        self.assertEqual(progress.state, "running")
        self.assertEqual(progress.target_branches, ["main", "feature"])
        self.assertEqual(progress.completed_batches, 3)
        self.assertEqual(progress.processed_commits, 150)


class TestIncrementalIndexer(unittest.TestCase):
    """Tests for IncrementalIndexer class."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.gimi_path = Path(self.temp_dir) / ".gimi"
        self.gimi_path.mkdir(parents=True)
        self.repo_root = Path(self.temp_dir) / "repo"
        self.repo_root.mkdir()

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creation(self):
        """Test creating an IncrementalIndexer."""
        config = LargeRepoConfig(
            max_commits=100,
            batch_size=10,
            branches=["main"]
        )

        indexer = IncrementalIndexer(self.gimi_path, self.repo_root, config)

        self.assertEqual(indexer.gimi_path, self.gimi_path)
        self.assertEqual(indexer.repo_root, self.repo_root)
        self.assertIsNotNone(indexer.config)

    def test_progress_save_and_load(self):
        """Test saving and loading progress."""
        config = LargeRepoConfig()
        indexer = IncrementalIndexer(self.gimi_path, self.repo_root, config)

        # Create a progress
        progress = IndexingProgress(
            state="running",
            target_branches=["main"],
            batch_size=50,
            total_batches=10,
            total_commits=500,
            started_at=datetime.now().isoformat()
        )

        # Add some batch progress
        for i in range(3):
            batch = BatchProgress(
                batch_number=i + 1,
                start_commit=f"commit{i}abc",
                end_commit=f"commit{i}xyz",
                commit_count=50,
                status="completed"
            )
            progress.batches.append(batch)
            progress.completed_batches += 1
            progress.processed_commits += 50

        # Save progress
        indexer._save_progress(progress)
        self.assertTrue(indexer.progress_path.exists())

        # Load progress
        loaded = indexer._load_progress()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.state, "running")
        self.assertEqual(loaded.target_branches, ["main"])
        self.assertEqual(loaded.completed_batches, 3)
        self.assertEqual(loaded.processed_commits, 150)
        self.assertEqual(len(loaded.batches), 3)

    def test_load_nonexistent_progress(self):
        """Test loading progress when file doesn't exist."""
        config = LargeRepoConfig()
        indexer = IncrementalIndexer(self.gimi_path, self.repo_root, config)

        loaded = indexer._load_progress()
        self.assertIsNone(loaded)


if __name__ == "__main__":
    unittest.main()
