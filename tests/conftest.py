"""
Pytest configuration and fixtures for Gimi tests.
"""
import os
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_git_repo(temp_dir):
    """Create a mock git repository structure."""
    git_dir = temp_dir / ".git"
    git_dir.mkdir()

    # Create minimal git structure
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    (git_dir / "refs" / "heads").mkdir(parents=True)

    return temp_dir


@pytest.fixture
def gimi_dir(mock_git_repo):
    """Create a .gimi directory structure."""
    gimi_path = mock_git_repo / ".gimi"
    gimi_path.mkdir(exist_ok=True)

    # Create subdirectories
    (gimi_path / "index").mkdir(exist_ok=True)
    (gimi_path / "vectors").mkdir(exist_ok=True)
    (gimi_path / "cache").mkdir(exist_ok=True)
    (gimi_path / "logs").mkdir(exist_ok=True)

    return gimi_path


@pytest.fixture
def sample_config():
    """Return a sample configuration dict."""
    return {
        "llm": {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "api_key_env": "ANTHROPIC_API_KEY"
        },
        "retrieval": {
            "top_k": 10,
            "candidate_pool_size": 50,
            "enable_two_stage_rerank": False
        },
        "context": {
            "max_files_per_commit": 10,
            "max_lines_per_file": 100,
            "max_total_commits": 5
        },
        "index": {
            "max_commits": 1000,
            "branches": ["main", "master"]
        },
        "observability": {
            "log_level": "INFO",
            "enable_metrics": True
        }
    }


@pytest.fixture
def sample_refs_snapshot():
    """Return a sample refs snapshot."""
    return {
        "main": "abc123def456",
        "feature-branch": "def789abc012"
    }


@pytest.fixture
def sample_commit_data():
    """Return sample commit metadata."""
    return {
        "hash": "abc123def456789",
        "message": "Fix authentication bug in login flow",
        "branch": "main",
        "timestamp": "2024-01-15T10:30:00Z",
        "files_changed": ["src/auth.py", "src/login.py", "tests/test_auth.py"],
        "author": "John Doe <john@example.com>"
    }


@pytest.fixture
def mock_embedding():
    """Return a mock embedding vector."""
    return [0.1] * 384  # 384-dimensional embedding


@pytest.fixture
def mock_llm_response():
    """Return a mock LLM response."""
    return {
        "suggestion": "Consider using a context manager for better resource handling.",
        "references": ["abc123def456", "def789abc012"],
        "confidence": 0.85
    }
