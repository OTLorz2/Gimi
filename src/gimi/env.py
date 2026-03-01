"""T1: Resolve repo root and ensure .gimi directory exists."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

# Subdirs under .gimi per plan
GIMI_SUBDIRS = ("index", "vectors", "cache", "logs")


def get_repo_root(cwd: Optional[os.PathLike[str]] = None) -> Path:
    """
    Resolve git repository root (same semantics as git: current dir or any parent).
    Raises RuntimeError if not inside a git repo.
    """
    cwd = Path(cwd or os.getcwd()).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(
            "Not inside a git repository. Run gimi from a path where git records can be queried."
        ) from e
    root = Path(out.stdout.strip()).resolve()
    if not root.is_dir():
        raise RuntimeError(f"Git repo root is not a directory: {root}")
    return root


def get_gimi_dir(repo_root: Optional[Path] = None) -> Path:
    """Return .gimi path at repo root; ensure repo_root is set."""
    if repo_root is None:
        repo_root = get_repo_root()
    return repo_root / ".gimi"


def ensure_gimi_dirs(repo_root: Optional[Path] = None) -> Path:
    """
    Ensure .gimi and its subdirs (index, vectors, cache, logs) exist.
    Does not write any business data.
    Returns the .gimi Path.
    """
    gimi = get_gimi_dir(repo_root)
    gimi.mkdir(parents=True, exist_ok=True)
    for sub in GIMI_SUBDIRS:
        (gimi / sub).mkdir(parents=True, exist_ok=True)
    return gimi
