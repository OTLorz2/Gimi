"""T6: Git walk - enumerate commits and yield metadata (no full diff)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from git import Repo


@dataclass
class CommitMeta:
    """Per-commit metadata for indexing."""
    hash: str
    message: str
    branch: str
    paths: List[str]
    author_time: int  # Unix timestamp


def _get_commit_paths(repo: Repo, commit_hexsha: str) -> List[str]:
    """Get list of changed file paths for a commit (no diff body)."""
    try:
        c = repo.commit(commit_hexsha)
        return [p for p in c.stats.files.keys()]
    except Exception:
        return []


def walk_commits(
    repo_root: Path,
    branches: Optional[List[str]] = None,
    max_commits: Optional[int] = None,
    batch_size: int = 500,
) -> Iterator[CommitMeta]:
    """
    Yield CommitMeta for each commit in the repo.
    - branches: if set, only these branches; else all local branches.
    - max_commits: stop after this many commits (per-branch or total depending on impl).
    - batch_size: not used for yielding but can be used by caller for batching.
    """
    repo = Repo(str(repo_root))
    if branches is None:
        branches = [ref.name for ref in repo.heads]
    seen_hashes: set = set()
    total = 0
    for branch_name in branches:
        try:
            ref = repo.heads[branch_name]
        except IndexError:
            continue
        for commit in repo.iter_commits(ref):
            if commit.hexsha in seen_hashes:
                continue
            seen_hashes.add(commit.hexsha)
            paths = _get_commit_paths(repo, commit.hexsha)
            author_time = commit.authored_date if hasattr(commit, "authored_date") else 0
            yield CommitMeta(
                hash=commit.hexsha,
                message=commit.message.strip() if commit.message else "",
                branch=branch_name,
                paths=paths,
                author_time=author_time,
            )
            total += 1
            if max_commits is not None and total >= max_commits:
                return
