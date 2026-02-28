"""Repository discovery and .gimi directory management."""

import os
import subprocess
from pathlib import Path
from typing import Optional


class RepoError(Exception):
    """Raised when repository operations fail."""
    pass


def find_repo_root(cwd: Optional[Path] = None) -> Path:
    """
    Find git repository root using git rev-parse --show-toplevel.

    Args:
        cwd: Starting directory, defaults to current working directory

    Returns:
        Path to repository root

    Raises:
        RepoError: If not inside a git repository
    """
    if cwd is None:
        cwd = Path.cwd()

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True
        )
        repo_root = Path(result.stdout.strip())
        return repo_root.resolve()
    except subprocess.CalledProcessError:
        raise RepoError(
            "Not a git repository (or any of the parent directories): .git\n"
            "Please run gimi inside a git repository."
        )
    except FileNotFoundError:
        raise RepoError("Git command not found. Please install git.")


def get_gimi_dir(repo_root: Optional[Path] = None) -> Path:
    """
    Get or create .gimi directory in repository root.

    Args:
        repo_root: Repository root path, defaults to finding it automatically

    Returns:
        Path to .gimi directory
    """
    if repo_root is None:
        repo_root = find_repo_root()

    gimi_dir = repo_root / ".gimi"
    return gimi_dir


def ensure_gimi_structure(repo_root: Optional[Path] = None) -> Path:
    """
    Ensure .gimi directory and all subdirectories exist.

    Creates:
        - .gimi/
        - .gimi/index/
        - .gimi/vectors/
        - .gimi/cache/
        - .gimi/logs/

    Args:
        repo_root: Repository root path

    Returns:
        Path to .gimi directory
    """
    gimi_dir = get_gimi_dir(repo_root)

    # Create all subdirectories
    subdirs = ["index", "vectors", "cache", "logs"]
    for subdir in subdirs:
        (gimi_dir / subdir).mkdir(parents=True, exist_ok=True)

    return gimi_dir
