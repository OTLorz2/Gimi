"""
Gimi - Auxiliary programming agent for git repositories.

Gimi is a CLI tool that helps developers understand and navigate
their codebase history using AI-powered commit search and analysis.

Usage:
    gimi index          # Build or update the commit index
    gimi search "query" # Search commits
    gimi ask "question" # Ask about the codebase

See `gimi --help` for more information.
"""

__version__ = "0.1.0"
__author__ = "Gimi Team"

from .repo import (
    find_repo_root,
    setup_gimi,
    GimiPaths,
    RepoError,
    NotAGitRepoError,
)

from .lock import (
    FileLock,
    GimiLockManager,
    LockError,
    LockAcquisitionError,
    LockHeldByOtherProcess,
    acquire_all,
)

from .cli import (
    GimiCLI,
    main,
)

__all__ = [
    # Version
    "__version__",
    # Repository
    "find_repo_root",
    "setup_gimi",
    "GimiPaths",
    "RepoError",
    "NotAGitRepoError",
    # Locking
    "FileLock",
    "GimiLockManager",
    "LockError",
    "LockAcquisitionError",
    "LockHeldByOtherProcess",
    "acquire_all",
    # CLI
    "GimiCLI",
    "main",
]
