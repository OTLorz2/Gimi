"""
Tests for repository parsing and .gimi directory creation (T1).
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from gimi.core.repo import (
    find_repo_root,
    get_gimi_dir,
    ensure_gimi_structure,
    GimiRepoError
)


class TestFindRepoRoot:
    """Tests for finding the git repository root."""

    def test_find_repo_root_success(self, temp_dir):
        """Test successfully finding repo root in current directory."""
        # Create a git repository
        git_dir = temp_dir / ".git"
        git_dir.mkdir()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=str(temp_dir) + '\n',
                stderr=''
            )
            result = find_repo_root()
            assert result == temp_dir

    def test_find_repo_root_from_subdirectory(self, temp_dir):
        """Test finding repo root from a subdirectory."""
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        subdir = temp_dir / "src" / "components"
        subdir.mkdir(parents=True)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=str(temp_dir) + '\n',
                stderr=''
            )
            result = find_repo_root(cwd=subdir)
            assert result == temp_dir

    def test_find_repo_root_not_git_repo(self, temp_dir):
        """Test error when not in a git repository."""
        from subprocess import CalledProcessError
        with patch('subprocess.run') as mock_run:
            # Configure mock to raise CalledProcessError when called with check=True
            mock_run.side_effect = CalledProcessError(
                returncode=128,
                cmd=['git', 'rev-parse', '--show-toplevel'],
                stderr='fatal: not a git repository'
            )
            with pytest.raises(GimiRepoError) as exc_info:
                find_repo_root()
            assert "not a git repository" in str(exc_info.value)

    def test_find_repo_root_subprocess_error(self):
        """Test handling of subprocess errors."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Command failed")
            with pytest.raises(GimiRepoError) as exc_info:
                find_repo_root()
            assert "Failed to find repository root" in str(exc_info.value)


class TestGetGimiDir:
    """Tests for getting .gimi directory path."""

    def test_get_gimi_dir(self, temp_dir):
        """Test getting .gimi directory path."""
        expected = temp_dir / ".gimi"
        result = get_gimi_dir(temp_dir)
        assert result == expected

    def test_get_gimi_dir_creates_nothing(self, temp_dir):
        """Test that get_gimi_dir doesn't create the directory."""
        gimi_dir = get_gimi_dir(temp_dir)
        assert not gimi_dir.exists()


class TestEnsureGimiStructure:
    """Tests for ensuring .gimi directory structure."""

    def test_ensure_structure_creates_all_dirs(self, temp_dir):
        """Test that all required directories are created."""
        gimi_dir = temp_dir / ".gimi"

        ensure_gimi_structure(temp_dir)

        assert gimi_dir.exists()
        assert (gimi_dir / "index").exists()
        assert (gimi_dir / "vectors").exists()
        assert (gimi_dir / "cache").exists()
        assert (gimi_dir / "logs").exists()

    def test_ensure_structure_idempotent(self, temp_dir):
        """Test that running ensure_structure multiple times is safe."""
        ensure_gimi_structure(temp_dir)
        ensure_gimi_structure(temp_dir)

        gimi_dir = temp_dir / ".gimi"
        assert gimi_dir.exists()
        assert (gimi_dir / "index").exists()

    def test_ensure_structure_creates_gimi_dir_first(self, temp_dir):
        """Test that .gimi directory is created before subdirectories."""
        gimi_dir = temp_dir / ".gimi"

        ensure_gimi_structure(temp_dir)

        # All subdirectories should be inside .gimi
        assert (gimi_dir / "index").exists()
        assert (gimi_dir / "index").parent == gimi_dir
