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

# Core modules - use core package
from .core.repo import (
    find_repo_root,
    ensure_gimi_structure,
    GimiRepoError,
    RepoError,
)

from .core.lock import (
    FileLock,
    LockError,
    LockTimeoutError,
)

from .core.config import (
    load_config,
    save_config,
    GimiConfig,
)

__all__ = [
    # Version
    "__version__",
    # Repository
    "find_repo_root",
    "ensure_gimi_structure",
    "GimiRepoError",
    "RepoError",
    # Locking
    "FileLock",
    "LockError",
    "LockTimeoutError",
    # Config
    "load_config",
    "save_config",
    "GimiConfig",
]
