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
    check_gimi_structure,
    get_gimi_dir,
    RepoError,
)

from .core.lock import (
    FileLock,
    LockError,
    LockTimeoutError,
    GimiLock,
    with_lock,
)

from .core.config import (
    load_config,
    save_config,
    init_config,
    GimiConfig,
    LLMConfig,
    RetrievalConfig,
    ContextConfig,
    IndexConfig,
    ConfigError,
)

__all__ = [
    # Version
    "__version__",
    # Repository
    "find_repo_root",
    "ensure_gimi_structure",
    "check_gimi_structure",
    "get_gimi_dir",
    "RepoError",
    # Locking
    "FileLock",
    "LockError",
    "LockTimeoutError",
    "GimiLock",
    "with_lock",
    # Config
    "load_config",
    "save_config",
    "init_config",
    "GimiConfig",
    "LLMConfig",
    "RetrievalConfig",
    "ContextConfig",
    "IndexConfig",
    "ConfigError",
]
