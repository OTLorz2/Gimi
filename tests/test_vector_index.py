"""Tests for vector index functionality (T8)."""

import tempfile
import unittest
from pathlib import Path
from datetime import datetime

import numpy as np

from gimi.vector_index import VectorIndex, SimpleEmbedding, VectorEntry
from gimi.git_traversal import CommitMeta


class TestSimpleEmbedding(unittest.TestCase):
    """Tests for SimpleEmbedding class."""

    def test_embed_dimensions(self):
        """Test embedding has correct dimensions."""
        embedder = SimpleEmbedding(dim=384)
        vector = embedder.embed("test text")
        self.assertEqual(len(vector), 384)

    def test_embed_normalization(self):
        """Test embedding is normalized."""
        embedder = SimpleEmbedding(dim=384)
        vector = embedder.embed("test text")
        norm = np.linalg.norm(vector)
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_embed_deterministic(self):
        """Test same text produces same embedding."""
        embedder = SimpleEmbedding(dim=384)
        vector1 = embedder.embed("test text")
        vector2 = embedder.embed("test text")
        np.testing.assert_array_almost_equal(vector1, vector2)

    def test_embed_batch(self):
        """Test batch embedding."""
        embedder = SimpleEmbedding(dim=384)
        texts = ["text 1", "text 2", "text 3"]
        vectors = embedder.embed_batch(texts)
        self.assertEqual(vectors.shape, (3, 384))


class TestVectorEntry(unittest.TestCase):
    """Tests for VectorEntry dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        entry = VectorEntry(
            commit_hash="abc123",
            vector=vector,
            text="test message"
        )
        data = entry.to_dict()
        self.assertEqual(data["commit_hash"], "abc123")
        self.assertEqual(data["text"], "test message")
        self.assertIn("vector", data)

    def test_from_dict(self):
        """Test creation from dictionary."""
        vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        data = {
            "commit_hash": "abc123",
            "vector": vector.tobytes().hex(),
            "text": "test message"
        }
        entry = VectorEntry.from_dict(data)
        self.assertEqual(entry.commit_hash, "abc123")
        self.assertEqual(entry.text, "test message")
        np.testing.assert_array_almost_equal(entry.vector, vector)


class TestVectorIndex(unittest.TestCase):
    """Tests for VectorIndex class."""

    def setUp(self):
        """Create temporary directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.gimi_path = Path(self.temp_dir) / ".gimi"
        self.gimi_path.mkdir(parents=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_index(self):
        """Test creating a vector index."""
        index = VectorIndex(self.gimi_path)
        self.assertEqual(index.get_entry_count(), 0)

    def test_add_commit(self):
        """Test adding a commit to the index."""
        index = VectorIndex(self.gimi_path)

        commit = CommitMeta(
            hash="abc123def456789012345678901234567890abcd",
            message="Test commit for authentication feature",
            author_name="Test User",
            author_email="test@example.com",
            author_date=datetime.now(),
            committer_name="Test User",
            committer_email="test@example.com",
            committer_date=datetime.now(),
            branches=["main"],
            parents=[],
            files_changed=["src/auth.py", "src/login.py"],
            stats={"insertions": 100, "deletions": 10, "files_changed": 2}
        )

        index.add_commit(commit)
        self.assertEqual(index.get_entry_count(), 1)

    def test_search(self):
        """Test searching the vector index."""
        index = VectorIndex(self.gimi_path)

        # Add test commits
        commits = [
            CommitMeta(
                hash=f"abc{i:03d}def456789012345678901234567890abcd",
                message=msg,
                author_name="Test User",
                author_email="test@example.com",
                author_date=datetime.now(),
                committer_name="Test User",
                committer_email="test@example.com",
                committer_date=datetime.now(),
                branches=["main"],
                parents=[],
                files_changed=["src/auth.py"],
                stats={"insertions": 10, "deletions": 0, "files_changed": 1}
            )
            for i, msg in enumerate([
                "Add user authentication feature",
                "Fix database connection timeout",
                "Update README with examples"
            ])
        ]

        for commit in commits:
            index.add_commit(commit)

        index.save()

        # Search
        results = index.search("authentication login", top_k=2)
        self.assertGreater(len(results), 0)
        self.assertLessEqual(len(results), 2)

        # Check similarity scores
        for commit_hash, similarity in results:
            self.assertGreaterEqual(similarity, -1.0)
            self.assertLessEqual(similarity, 1.0)

    def test_save_and_load(self):
        """Test saving and loading the index."""
        index1 = VectorIndex(self.gimi_path)

        commit = CommitMeta(
            hash="abc123def456789012345678901234567890abcd",
            message="Test commit",
            author_name="Test User",
            author_email="test@example.com",
            author_date=datetime.now(),
            committer_name="Test User",
            committer_email="test@example.com",
            committer_date=datetime.now(),
            branches=["main"],
            parents=[],
            files_changed=["src/test.py"],
            stats={"insertions": 10, "deletions": 0, "files_changed": 1}
        )

        index1.add_commit(commit)
        index1.save()

        # Load in new instance
        index2 = VectorIndex(self.gimi_path)
        self.assertEqual(index2.get_entry_count(), 1)


if __name__ == "__main__":
    unittest.main()
