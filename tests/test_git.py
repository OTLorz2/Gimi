"""Tests for git operations."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from gimi.core.git import (
    CommitMetadata,
    GitError,
    get_current_branch,
    get_branches,
    get_commits_for_branch,
    get_commit_metadata,
    get_commit_files,
    get_commit_diff,
)


class TestGitOperations(unittest.TestCase):
    """Tests for git operations."""

    def setUp(self):
        """Create a temporary git repository."""
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = Path(self.temp_dir) / "test_repo"
        self.repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )

        # Configure git user
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )

        # Create initial commit
        test_file = self.repo_dir / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(
            ["git", "add", "."],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_current_branch(self):
        """Test getting current branch."""
        branch = get_current_branch(self.repo_dir)
        self.assertEqual(branch, "master")

    def test_get_branches(self):
        """Test getting list of branches."""
        branches = get_branches(self.repo_dir)
        self.assertIn("master", branches)

    def test_get_commits_for_branch(self):
        """Test getting commits for a branch."""
        commits = get_commits_for_branch(self.repo_dir, "master")
        self.assertEqual(len(commits), 1)

    def test_get_commit_metadata(self):
        """Test getting commit metadata."""
        commits = get_commits_for_branch(self.repo_dir, "master")
        meta = get_commit_metadata(self.repo_dir, commits[0])

        self.assertIsNotNone(meta)
        self.assertEqual(meta.message, "Initial commit")
        self.assertEqual(meta.author, "Test User")
        self.assertEqual(meta.author_email, "test@test.com")

    def test_get_commit_files(self):
        """Test getting files changed in a commit."""
        commits = get_commits_for_branch(self.repo_dir, "master")
        files = get_commit_files(self.repo_dir, commits[0])

        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], "test.txt")


class TestCommitMetadata(unittest.TestCase):
    """Tests for CommitMetadata dataclass."""

    def test_short_hash(self):
        """Test short hash property."""
        meta = CommitMetadata(
            hash="abc123def456789",
            message="Test commit",
            author="Test",
            author_email="test@test.com",
            author_date="2024-01-01",
            committer="Test",
            committer_email="test@test.com",
            committer_date="2024-01-01",
        )
        self.assertEqual(meta.short_hash, "abc123d")

    def test_to_dict(self):
        """Test conversion to dictionary."""
        meta = CommitMetadata(
            hash="abc123",
            message="Test",
            author="Test",
            author_email="test@test.com",
            author_date="2024-01-01",
            committer="Test",
            committer_email="test@test.com",
            committer_date="2024-01-01",
            parents=["def456"],
            branches=["main"],
            changed_files=["file.txt"]
        )
        data = meta.to_dict()
        self.assertEqual(data["hash"], "abc123")
        self.assertEqual(data["parents"], ["def456"])


if __name__ == "__main__":
    unittest.main()
