"""T4: Config load and refs snapshot format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Config keys (non-sensitive only; API key from env GIMI_API_KEY)
CONFIG_FILENAME = "config.json"
REFS_SNAPSHOT_FILENAME = "refs_snapshot.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "model": "gpt-4o-mini",
    "top_k": 20,
    "candidate_size": 80,
    "max_diff_lines_per_file": 80,
    "max_files_per_commit": 10,
    "max_commits_indexed": 2000,
    "index_batch_size": 100,
    "branches": None,  # None = all; or ["main", "develop"]
    "enable_rerank": False,
    "rerank_top": 8,
}


def load_config(gimi_dir: Path) -> Dict[str, Any]:
    """Load config from .gimi/config.json; merge with defaults; return dict."""
    path = gimi_dir / CONFIG_FILENAME
    cfg = dict(DEFAULT_CONFIG)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cfg.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_config(gimi_dir: Path, config: Dict[str, Any]) -> None:
    """Save config to .gimi/config.json (only non-sensitive fields)."""
    path = gimi_dir / CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


# Refs snapshot: { "branch_name": "commit_hash", ... }
RefsSnapshot = Dict[str, str]


def load_refs_snapshot(gimi_dir: Path) -> Optional[RefsSnapshot]:
    """Load refs snapshot from .gimi/refs_snapshot.json; return None if missing or invalid."""
    path = gimi_dir / REFS_SNAPSHOT_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
            return data
        return None
    except (json.JSONDecodeError, OSError):
        return None


def save_refs_snapshot(gimi_dir: Path, snapshot: RefsSnapshot) -> None:
    """Save refs snapshot after index build/update."""
    path = gimi_dir / REFS_SNAPSHOT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
