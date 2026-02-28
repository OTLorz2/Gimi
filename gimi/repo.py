"""
T1: Repository parsing and .gimi directory creation.

This module handles:
- Finding the git repository root from any subdirectory
- Creating and managing the .gimi directory structure
- Path utilities for the .gimi subdirectories
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


class RepoError(Exception):
    """Raised when there's an issue with repository operations."""
    pass


class NotAGitRepoError(RepoError):
    """Raised when the current directory is not in a git repository."""
    pass


def find_repo_root(cwd: Optional[Path] = None) -> Path:
    """
    Find the git repository root using git rev-parse.

    Args:
        cwd: Current working directory. If None, uses os.getcwd().

    Returns:
        Path to the repository root.

    Raises:
        NotAGitRepoError: If not in a git repository.
        RepoError: If git command fails for other reasons.
    """
    if cwd is None:
        cwd = Path.cwd()

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True
        )
        repo_root = Path(result.stdout.strip())
        return repo_root.resolve()
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.lower() if e.stderr else ""
        if 'not a git repository' in stderr or 'not a git repo' in stderr:
            raise NotAGitRepoError(
                "Not a git repository. Please run gimi inside a git repository."
            )
        raise RepoError(f"Failed to find repository root: {e.stderr}")
    except FileNotFoundError:
        raise RepoError("git command not found. Please install git.")


class GimiPaths:
    """
    Manages paths within the .gimi directory.

    Provides easy access to:
    - config.json
    - index/ (lightweight index)
    - vectors/ (vector index)
    - cache/ (commit diff cache)
    - logs/ (observability logs)
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.gimi_dir = self.repo_root / '.gimi'

    @property
    def config(self) -> Path:
        """Path to config.json."""
        return self.gimi_dir / 'config.json'

    @property
    def index_dir(self) -> Path:
        """Directory for lightweight index."""
        return self.gimi_dir / 'index'

    @property
    def vectors_dir(self) -> Path:
        """Directory for vector index."""
        return self.gimi_dir / 'vectors'

    @property
    def cache_dir(self) -> Path:
        """Directory for commit diff cache."""
        return self.gimi_dir / 'cache'

    @property
    def logs_dir(self) -> Path:
        """Directory for observability logs."""
        return self.gimi_dir / 'logs'

    def ensure_dirs(self) -> None:
        """
        Create the .gimi directory and all subdirectories if they don't exist.
        Safe to call multiple times (idempotent).
        """
        for path in [self.gimi_dir, self.index_dir, self.vectors_dir,
                     self.cache_dir, self.logs_dir]:
            path.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        """Check if .gimi directory exists."""
        return self.gimi_dir.exists()


def setup_gimi(repo_root: Optional[Path] = None,
               cwd: Optional[Path] = None) -> Tuple[Path, GimiPaths]:
    """
    Complete setup: find repo root and ensure .gimi directory exists.

    Args:
        repo_root: If provided, use this path. Otherwise find it from cwd.
        cwd: Current working directory for finding repo root.

    Returns:
        Tuple of (repo_root, GimiPaths instance)

    Raises:
        NotAGitRepoError: If not in a git repository.
    """
    if repo_root is None:
        repo_root = find_repo_root(cwd)

    gimi_paths = GimiPaths(repo_root)
    gimi_paths.ensure_dirs()

    return repo_root, gimi_paths


if __name__ == '__main__':
    # Simple test
    try:
        repo_root, paths = setup_gimi()
        print(f"Repository root: {repo_root}")
        print(f".gimi directory: {paths.gimi_dir}")
        print(f"Config path: {paths.config}")
        print(f"Index dir: {paths.index_dir}")
        print(f"Vectors dir: {paths.vectors_dir}")
        print(f"Cache dir: {paths.cache_dir}")
        print(f"Logs dir: {paths.logs_dir}")
    except NotAGitRepoError as e:
        print(f"Error: {e}")
    except RepoError as e:
        print(f"Repository error: {e}")
