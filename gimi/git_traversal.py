"""
Git traversal and commit metadata extraction (T6).

This module provides functions for traversing git history and extracting
commit metadata. It serves as a compatibility layer that re-exports
core git functionality.
"""

# Re-export from core.git for backward compatibility
from gimi.core.git import (
    CommitMetadata,
    CommitMetadata as CommitMeta,  # Alias for compatibility with tests
    get_commit_metadata,
    get_commit_files,
    get_commits_for_branch,
    get_branches,
    get_current_branch,
)

__all__ = [
    "CommitMetadata",
    "CommitMeta",  # Compatibility alias
    "get_commit_metadata",
    "get_commit_files",
    "get_commits_for_branch",
    "get_branches",
    "get_current_branch",
]
