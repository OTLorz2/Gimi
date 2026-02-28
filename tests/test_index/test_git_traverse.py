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
            author_name="John Doe",
            author_email="john@example.com",
            author_timestamp=1642320600,
        )

        assert metadata.hash == "abc123def456"
        assert metadata.message == "Fix bug in auth"
        assert metadata.author_name == "John Doe"

    def test_commit_metadata_to_dict(self):
        """Test converting CommitMetadata to dict."""
        metadata = CommitMetadata(
            hash="abc123",
            message="Test",
            author_name="Test",
            author_email="test@example.com",
            author_timestamp=1642320600,
            files_changed=["file.py"],
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
            "author_name": "Test",
            "author_email": "test@example.com",
            "author_timestamp": 1642320600,
            "files_changed": ["file.py"],
        }

        metadata = CommitMetadata.from_dict(data)

        assert metadata.hash == "abc123"
        assert metadata.message == "Test"


class TestGitTraversal:
    """Tests for GitTraversal class."""

    def test_init(self, temp_dir):
        """Test GitTraversal initialization."""
        traversal = GitTraversal(temp_dir)
        assert traversal.repo_root == temp_dir

    def test_run_git_success(self, temp_dir):
        """Test successful git command execution."""
        traversal = GitTraversal(temp_dir)

        # Create a mock result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result):
            result = traversal._run_git(['status'])
            assert result.returncode == 0
            assert result.stdout == "test output"

    def test_run_git_error(self, temp_dir):
        """Test git command error handling."""
        traversal = GitTraversal(temp_dir)

        # Create a mock result with error
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "fatal: not a git repository"

        with patch('subprocess.run', return_value=mock_result):
            with pytest.raises(GitTraversalError):
                traversal._run_git(['status'])


class TestGitTraversalTraversal:
    """Tests for commit traversal functionality."""

    def test_traverse_commits_basic(self, temp_dir):
        """Test basic commit traversal."""
        traversal = GitTraversal(temp_dir)

        # Mock the _run_git method to return sample git log output
        # The parser expects a specific format - each commit is parsed from one line
        mock_output = """abc123def456|John Doe|john@example.com|1642320600|John Doe|john@example.com|1642320600|parent1|First commit
1	1	file1.txt"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = mock_output

        with patch.object(traversal, '_run_git', return_value=mock_result):
            commits = list(traversal.traverse_commits(branches=["main"]))
            assert len(commits) == 1
            assert commits[0].hash == "abc123def456"
            assert commits[0].message == "First commit"
            assert commits[0].author_name == "John Doe"


class TestGitTraversalBranches:
    """Tests for branch-related functionality."""

    def test_get_branches(self, temp_dir):
        """Test getting list of branches."""
        traversal = GitTraversal(temp_dir)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "main\ndevelop\nfeature/test\n"

        with patch.object(traversal, '_run_git', return_value=mock_result):
            branches = traversal.get_branches()
            assert "main" in branches
            assert "develop" in branches
            assert "feature/test" in branches
