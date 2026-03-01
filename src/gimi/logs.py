"""T16: Observability logging to .gimi/logs/."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _log_dir(gimi_dir: Path) -> Path:
    return gimi_dir / "logs"


def _log_file(gimi_dir: Path) -> Path:
    return _log_dir(gimi_dir) / "gimi.log"


def init_request_log(
    gimi_dir: Path,
    repo_root: Path,
    index_reused: bool,
) -> str:
    """Create a request id and log start; return request_id."""
    request_id = str(uuid.uuid4())[:8]
    _log_dir(gimi_dir).mkdir(parents=True, exist_ok=True)
    with open(_log_file(gimi_dir), "a", encoding="utf-8") as f:
        f.write(
            f"{datetime.utcnow().isoformat()}Z [{request_id}] repo_root={repo_root} index_reused={index_reused}\n"
        )
    return request_id


def log_request_end(
    gimi_dir: Path,
    request_id: str,
    candidate_size: int,
    top_k: int,
    context_chars: int,
    llm_elapsed_sec: Optional[float] = None,
) -> None:
    """Append request end metrics to log file."""
    with open(_log_file(gimi_dir), "a", encoding="utf-8") as f:
        line = f"{datetime.utcnow().isoformat()}Z [{request_id}] candidate_size={candidate_size} top_k={top_k} context_chars={context_chars}"
        if llm_elapsed_sec is not None:
            line += f" llm_elapsed_sec={llm_elapsed_sec:.2f}"
        f.write(line + "\n")
