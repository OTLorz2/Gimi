"""
Repository parsing and .gimi directory creation (T1).

This module handles:
- Finding the git repository root
- Creating and managing the .gimi directory structure
"""
import subprocess
import os
from pathlib import Path
from typing import Optional


class RepoError(Exception):
    """Error related to repository operations."""
    pass


# Alias for backward compatibility
GimiRepoError = RepoError


def find_repo_root(cwd: Optional[Path] = None) -> Path:
    """
    Find the root of the git repository.

    Uses `git rev-parse --show-toplevel` to find the repository root.
    If not in a git repository, raises GimiRepoError.

    Args:
        cwd: Current working directory. If None, uses os.getcwd().

    Returns:
        Path to the repository root.

    Raises:
        GimiRepoError: If not in a git repository or git command fails.
    """
    if cwd is None:
        cwd = Path.cwd()

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else "Not a git repository"
        raise GimiRepoError(f"Failed to find repository root: {error_msg}")
    except Exception as e:
        raise GimiRepoError(f"Failed to find repository root: {e}")


def get_gimi_dir(repo_root: Path) -> Path:
    """
    Get the path to the .gimi directory.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Path to the .gimi directory.
    """
    return repo_root / ".gimi"


def ensure_gimi_structure(repo_root: Path) -> Path:
    """
    Ensure the .gimi directory structure exists.

    Creates the following structure:
    .gimi/
    ├── index/       # Lightweight index (commit meta + paths)
    ├── vectors/     # Vector index (embeddings)
    ├── cache/       # Commit diff cache
    └── logs/        # Runtime logs

    Args:
        repo_root: Path to the repository root.

    Returns:
        Path to the .gimi directory.

    Raises:
        GimiRepoError: If unable to create directories.
    """
    gimi_dir = get_gimi_dir(repo_root)

    subdirs = ["index", "vectors", "cache", "logs"]

    try:
        # Create main .gimi directory
        gimi_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        for subdir in subdirs:
            (gimi_dir / subdir).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise GimiRepoError(f"Failed to create .gimi structure: {e}")

    return gimi_dir


def check_gimi_structure(repo_root: Path) -> bool:
    """
    Check if the .gimi directory structure exists and is valid.

    Args:
        repo_root: Path to the repository root.

    Returns:
        True if structure exists and is valid, False otherwise.
    """
    gimi_dir = get_gimi_dir(repo_root)

    if not gimi_dir.exists():
        return False

    required_subdirs = ["index", "vectors", "cache", "logs"]

    for subdir in required_subdirs:
        if not (gimi_dir / subdir).exists():
            return False

    return True
