"""
Tests for Git traversal and commit metadata extraction (T6).
"""
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from gimi.index.git import (
    traverse_commits,
    get_commit_metadata,
    get_changed_files,
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

        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.return_value = expected_commits

            result = list(traverse_commits(temp_dir, branch="main"))

            assert len(result) == 2

    def test_traverse_with_limit(self, temp_dir):
        """Test traversing with commit limit."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.return_value = [f"commit{i}" for i in range(100)]

            result = list(traverse_commits(temp_dir, max_commits=10))

            assert len(result) == 10

    def test_traverse_since_date(self, temp_dir):
        """Test traversing since a specific date."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.return_value = ["commit1", "commit2"]

            list(traverse_commits(temp_dir, since="2024-01-01"))

            # Verify git command was called with since parameter
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0]
            assert '--since' in call_args[1]

    def test_traverse_branches(self, temp_dir):
        """Test traversing multiple branches."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.return_value = ["commit1", "commit2"]

            result = list(traverse_commits(temp_dir, branches=["main", "develop"]))

            assert len(result) == 2

    def test_traverse_git_error(self, temp_dir):
        """Test handling of git errors during traversal."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.side_effect = Exception("Git error")

            with pytest.raises(GitTraversalError) as exc_info:
                list(traverse_commits(temp_dir))

            assert "Failed to traverse commits" in str(exc_info.value)


class TestGetCommitMetadata:
    """Tests for commit metadata extraction."""

    def test_get_commit_metadata_success(self, temp_dir):
        """Test successfully getting commit metadata."""
        commit_hash = "abc123def456"

        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.side_effect = [
                ["Fix authentication bug"],  # message
                ["2024-01-15T10:30:00Z"],    # timestamp
                ["John Doe <john@example.com>"],  # author
                ["src/auth.py", "tests/test_auth.py"]  # files
            ]

            result = get_commit_metadata(temp_dir, commit_hash, branch="main")

            assert result.hash == commit_hash
            assert result.message == "Fix authentication bug"
            assert result.branch == "main"
            assert result.files_changed == ["src/auth.py", "tests/test_auth.py"]

    def test_get_commit_metadata_empty_message(self, temp_dir):
        """Test handling commit with empty message."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.side_effect = [
                [""],  # empty message
                ["2024-01-15T10:30:00Z"],
                ["Author"],
                ["file.py"]
            ]

            result = get_commit_metadata(temp_dir, "abc123", branch="main")

            assert result.message == ""

    def test_get_commit_metadata_no_files(self, temp_dir):
        """Test handling commit with no file changes."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.side_effect = [
                ["Initial commit"],
                ["2024-01-15T10:30:00Z"],
                ["Author"],
                []  # no files
            ]

            result = get_commit_metadata(temp_dir, "abc123", branch="main")

            assert result.files_changed == []

    def test_get_commit_metadata_git_error(self, temp_dir):
        """Test handling git errors."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.side_effect = Exception("Git error")

            with pytest.raises(GitTraversalError) as exc_info:
                get_commit_metadata(temp_dir, "abc123", branch="main")

            assert "Failed to get commit metadata" in str(exc_info.value)


class TestGetChangedFiles:
    """Tests for getting changed files in a commit."""

    def test_get_changed_files_success(self, temp_dir):
        """Test successfully getting changed files."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.return_value = [
                "src/auth.py",
                "tests/test_auth.py",
                "README.md"
            ]

            result = get_changed_files(temp_dir, "abc123")

            assert result == ["src/auth.py", "tests/test_auth.py", "README.md"]

    def test_get_changed_files_empty(self, temp_dir):
        """Test getting changed files for commit with no changes."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.return_value = []

            result = get_changed_files(temp_dir, "abc123")

            assert result == []

    def test_get_changed_files_with_status(self, temp_dir):
        """Test getting changed files with status."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.return_value = [
                "M\tsrc/auth.py",
                "A\ttests/test_auth.py",
                "D\tREADME.md"
            ]

            result = get_changed_files(temp_dir, "abc123", include_status=True)

            assert len(result) == 3
            assert result[0] == {"status": "M", "file": "src/auth.py"}
            assert result[1] == {"status": "A", "file": "tests/test_auth.py"}
            assert result[2] == {"status": "D", "file": "README.md"}

    def test_get_changed_files_git_error(self, temp_dir):
        """Test handling git errors."""
        with patch('gimi.index.git.run_git_command') as mock_run:
            mock_run.side_effect = Exception("Git error")

            with pytest.raises(GitTraversalError) as exc_info:
                get_changed_files(temp_dir, "abc123")

            assert "Failed to get changed files" in str(exc_info.value)
