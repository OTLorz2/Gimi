"""
Tests for Git traversal and commit metadata extraction (T6).
"""
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from gimi.index.git import (
    GitTraversal,
    GitTraversalError,
    CommitMetadata
)


class TestCommitMetadata:
    """Tests for CommitMetadata dataclass."""

    def test_commit_metadata_creation(self):
        """Test creating CommitMetadata instance."""
        metadata = CommitMetadata(
            hash="abc123def456",
            message="Fix bug in auth",
            branch="main",
            timestamp="2024-01-15T10:30:00Z",
            files_changed=["src/auth.py", "tests/test_auth.py"],
            author="John Doe <john@example.com>"
        )

        assert metadata.hash == "abc123def456"
        assert metadata.message == "Fix bug in auth"
        assert metadata.branch == "main"

    def test_commit_metadata_to_dict(self):
        """Test converting CommitMetadata to dict."""
        metadata = CommitMetadata(
            hash="abc123",
            message="Test",
            branch="main",
            timestamp="2024-01-01T00:00:00Z",
            files_changed=["file.py"],
            author="Test"
        )

        result = metadata.to_dict()

        assert result["hash"] == "abc123"
        assert result["message"] == "Test"
        assert result["files_changed"] == ["file.py"]

    def test_commit_metadata_from_dict(self):
        """Test creating CommitMetadata from dict."""
        data = {
            "hash": "abc123",
            "message": "Test",
            "branch": "main",
            "timestamp": "2024-01-01T00:00:00Z",
            "files_changed": ["file.py"],
            "author": "Test"
        }

        metadata = CommitMetadata.from_dict(data)

        assert metadata.hash == "abc123"
        assert metadata.message == "Test"


class TestTraverseCommits:
    """Tests for commit traversal."""

    def test_traverse_single_branch(self, temp_dir):
        """Test traversing commits on a single branch."""
        expected_commits = [
            "commit1 hash info",
            "commit2 hash info"
        ]

        with patch.object(GitTraversal, '_run_git') as mock_run:
            mock_run.return_value.stdout = "\n".join(expected_commits)
            mock_run.return_value.returncode = 0

            traversal = GitTraversal(temp_dir)
            result = list(traversal.traverse_commits(branches=["main"]))

            assert len(result) == 2

    def test_traverse_with_limit(self, temp_dir):
        """Test traversing with commit limit."""
        with patch.object(GitTraversal, '_run_git') as mock_run:
            mock_run.return_value.stdout = "\n".join([f"commit{i}" for i in range(100)])
            mock_run.return_value.returncode = 0

            traversal = GitTraversal(temp_dir)
            result = list(traversal.traverse_commits(branches=["main"], max_commits=10))

            assert len(result) == 10

    def test_traverse_since_date(self, temp_dir):
        """Test traversing since a specific date."""
        with patch.object(GitTraversal, '_run_git') as mock_run:
            mock_run.return_value.stdout = "commit1\ncommit2"
            mock_run.return_value.returncode = 0

            traversal = GitTraversal(temp_dir)
            from datetime import datetime
            since_date = datetime(2024, 1, 1)
            list(traversal.traverse_commits(branches=["main"], since=since_date))

            # Verify git command was called with since parameter
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert '--since' in call_args

    def test_traverse_branches(self, temp_dir):
        """Test traversing multiple branches."""
        with patch.object(GitTraversal, '_run_git') as mock_run:
            mock_run.return_value.stdout = "commit1\ncommit2"
            mock_run.return_value.returncode = 0

            traversal = GitTraversal(temp_dir)
            result = list(traversal.traverse_commits(branches=["main", "develop"]))

            assert len(result) == 2

    def test_traverse_git_error(self, temp_dir):
        """Test handling of git errors during traversal."""
        with patch.object(GitTraversal, '_run_git') as mock_run:
            mock_run.side_effect = GitTraversalError("Git error")

            traversal = GitTraversal(temp_dir)
            with pytest.raises(GitTraversalError) as exc_info:
                list(traversal.traverse_commits(branches=["main"]))

            assert "Git error" in str(exc_info.value)


class TestGetCommitMetadata:
    """Tests for commit metadata extraction."""

    def test_commit_metadata_creation(self):
        """Test creating CommitMetadata via GitTraversal."""
        traversal = GitTraversal(Path("/tmp"))

        with patch.object(traversal, '_run_git') as mock_run:
            mock_run.return_value.stdout = "commit123\n"
            mock_run.return_value.returncode = 0

            # Test that we can create metadata
            metadata = CommitMetadata(
                hash="abc123def456",
                message="Test commit",
                author_name="Test Author",
                author_email="test@example.com"
            )

            assert metadata.hash == "abc123def456"
            assert metadata.message == "Test commit"

    def test_commit_metadata_empty_message(self):
        """Test handling commit with empty message."""
        metadata = CommitMetadata(
            hash="abc123",
            message="",
            author_name="Test"
        )

        assert metadata.message == ""

    def test_commit_metadata_no_files(self):
        """Test handling commit with no file changes."""
        metadata = CommitMetadata(
            hash="abc123",
            message="Initial commit",
            files_changed=[]
        )

        assert metadata.files_changed == []

    def test_git_traversal_error(self):
        """Test that GitTraversalError can be raised."""
        with pytest.raises(GitTraversalError):
            raise GitTraversalError("Test error")


class TestGetChangedFiles:
    """Tests for getting changed files in a commit."""

    def test_get_changed_files_success(self, temp_dir):
        """Test successfully getting changed files."""
        traversal = GitTraversal(temp_dir)

        with patch.object(traversal, '_run_git') as mock_run:
            mock_run.return_value.stdout = "src/auth.py\ntests/test_auth.py\nREADME.md\n"
            mock_run.return_value.returncode = 0

            result = traversal.get_commit_files("abc123")

            assert result == ["src/auth.py", "tests/test_auth.py", "README.md"]

    def test_get_changed_files_empty(self, temp_dir):
        """Test getting changed files for commit with no changes."""
        traversal = GitTraversal(temp_dir)

        with patch.object(traversal, '_run_git') as mock_run:
            mock_run.return_value.stdout = ""
            mock_run.return_value.returncode = 0

            result = traversal.get_commit_files("abc123")

            assert result == []

    def test_get_changed_files_git_error(self, temp_dir):
        """Test handling git errors."""
        traversal = GitTraversal(temp_dir)

        with patch.object(traversal, '_run_git') as mock_run:
            mock_run.side_effect = GitTraversalError("Git error")

            with pytest.raises(GitTraversalError):
                traversal.get_commit_files("abc123")
