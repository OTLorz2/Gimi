"""Get current repo refs (branch -> HEAD hash) for index validity check."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional

from .config import RefsSnapshot, load_refs_snapshot


def get_current_refs(repo_root: Path) -> RefsSnapshot:
    """Return dict of branch_name -> commit_hash for all branches (local refs/heads)."""
    try:
        out = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    result: Dict[str, str] = {}
    for line in out.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            result[parts[0]] = parts[1]
    return result


def is_index_stale(repo_root: Path, gimi_dir: Path) -> bool:
    """
    Compare current repo refs with saved refs snapshot.
    Return True if index should be considered stale (need rebuild or incremental).
    """
    current = get_current_refs(repo_root)
    saved = load_refs_snapshot(gimi_dir)
    if saved is None:
        return True
    if set(current.keys()) != set(saved.keys()):
        return True
    for branch, hash_val in current.items():
        if saved.get(branch) != hash_val:
            return True
    return False
