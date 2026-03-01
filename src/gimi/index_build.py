"""T9: Index build - orchestrate git walk, lightweight index, vector index, refs snapshot; batch and resume."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import load_config, save_refs_snapshot, RefsSnapshot
from .env import get_gimi_dir
from .git_walk import CommitMeta, walk_commits
from .lightweight_index import open_index, write_commits_batch, clear_index, get_all_hashes
from .lock import write_lock
from .refs import get_current_refs
from .vector_index import get_embedding, open_vectors, write_embedding

# Progress file for resumable build
PROGRESS_FILE = "index/progress.json"


def _text_for_embedding(meta: CommitMeta) -> str:
    return meta.message + " " + " ".join(meta.paths)


def load_progress(gimi_dir: Path) -> Optional[Dict[str, Any]]:
    path = gimi_dir / PROGRESS_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_progress(gimi_dir: Path, data: Dict[str, Any]) -> None:
    path = gimi_dir / PROGRESS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=0), encoding="utf-8")


def remove_progress(gimi_dir: Path) -> None:
    (gimi_dir / PROGRESS_FILE).unlink(missing_ok=True)


def build_index(
    repo_root: Path,
    gimi_dir: Optional[Path] = None,
    force_full: bool = False,
    api_key: Optional[str] = None,
) -> None:
    """
    Build or resume index: walk commits (with config limits), write lightweight + vector index,
    then save refs snapshot. Uses write lock. On resume, continues from progress file.
    """
    gimi_dir = gimi_dir or get_gimi_dir(repo_root)
    config = load_config(gimi_dir)
    max_commits = config.get("max_commits_indexed") or 2000
    batch_size = config.get("index_batch_size") or 100
    branches = config.get("branches")

    with write_lock(gimi_dir):
        progress = None if force_full else load_progress(gimi_dir)
        if progress is None:
            # Full build: clear and start
            conn_light = open_index(gimi_dir)
            try:
                clear_index(conn_light)
            finally:
                conn_light.close()
            seen_hashes: set = set()
            total_written = 0
        else:
            seen_hashes = set(progress.get("seen_hashes", []))
            total_written = progress.get("total_written", 0)
            if total_written >= max_commits:
                # Already done
                _finalize_index(repo_root, gimi_dir)
                return

        conn_light = open_index(gimi_dir)
        conn_vec = open_vectors(gimi_dir)
        try:
            batch: List[CommitMeta] = []
            for meta in walk_commits(repo_root, branches=branches, max_commits=max_commits):
                if meta.hash in seen_hashes:
                    continue
                seen_hashes.add(meta.hash)
                batch.append(meta)
                if len(batch) >= batch_size:
                    write_commits_batch(conn_light, batch)
                    for c in batch:
                        text = _text_for_embedding(c)
                        emb = get_embedding(text, api_key=api_key or os.environ.get("GIMI_API_KEY"))
                        write_embedding(conn_vec, c.hash, emb)
                    total_written += len(batch)
                    save_progress(gimi_dir, {"seen_hashes": list(seen_hashes), "total_written": total_written})
                    batch = []
                    if total_written >= max_commits:
                        break
            if batch:
                write_commits_batch(conn_light, batch)
                for c in batch:
                    text = _text_for_embedding(c)
                    emb = get_embedding(text, api_key=api_key or os.environ.get("GIMI_API_KEY"))
                    write_embedding(conn_vec, c.hash, emb)
                total_written += len(batch)
            remove_progress(gimi_dir)
            _finalize_index(repo_root, gimi_dir)
        finally:
            conn_light.close()
            conn_vec.close()


def _finalize_index(repo_root: Path, gimi_dir: Path) -> None:
    """Write refs snapshot after index build."""
    snapshot: RefsSnapshot = get_current_refs(repo_root)
    save_refs_snapshot(gimi_dir, snapshot)
