"""T5: Index validity check at startup."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from .refs import is_index_stale


def check_index_validity(repo_root: Path, gimi_dir: Path) -> Tuple[bool, bool]:
    """
    Compare current repo refs with saved snapshot.
    Returns (index_usable, need_rebuild).
    - index_usable: False if we should not use existing index (stale or missing).
    - need_rebuild: True if index is stale and we should trigger rebuild/incremental.
    """
    stale = is_index_stale(repo_root, gimi_dir)
    if stale:
        return False, True
    # Check that index dir has data (lightweight index exists)
    index_dir = gimi_dir / "index"
    index_usable = (index_dir / "commits.db").exists() if index_dir.exists() else False
    return index_usable, False
