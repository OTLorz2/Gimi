"""T13: Fetch diff for Top-K commits and truncate by config."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from git import Repo


def get_diff(repo_root: Path, commit_hash: str) -> str:
    """Get full diff for one commit (git show)."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "show", "--no-color", commit_hash, "--"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout or ""
    except Exception:
        try:
            repo = Repo(str(repo_root))
            return repo.git.show(commit_hash, "--no-color")
        except Exception:
            return ""


def _truncate_diff(
    diff_text: str,
    max_lines_per_file: int,
    max_files: int,
) -> str:
    """Truncate diff: keep at most max_files files, each at most max_lines_per_file lines."""
    if not diff_text.strip():
        return diff_text
    files = diff_text.split("diff --git ")
    out = []
    for i, block in enumerate(files):
        if not block.strip():
            continue
        if i >= max_files:
            out.append("\n... (more files omitted)\n")
            break
        lines = block.splitlines()
        kept = lines[: max_lines_per_file + 1]
        if len(lines) > max_lines_per_file:
            kept.append(f"... ({len(lines) - max_lines_per_file} more lines)\n")
        out.append("diff --git " + "\n".join(kept))
    return "\n".join(out).strip()


def fetch_diffs_for_commits(
    repo_root: Path,
    commit_hashes: List[str],
    max_diff_lines_per_file: int = 80,
    max_files_per_commit: int = 10,
) -> List[Tuple[str, str]]:
    """
    For each commit in commit_hashes, fetch diff and truncate. Returns list of (commit_hash, truncated_diff).
    """
    result: List[Tuple[str, str]] = []
    for h in commit_hashes:
        raw = get_diff(repo_root, h)
        truncated = _truncate_diff(raw, max_diff_lines_per_file, max_files_per_commit)
        result.append((h, truncated))
    return result


def get_diff_repr(diff_output: str) -> str:
    """Convert GitPython DiffIndex to string if needed."""
    if hasattr(diff_output, "decode"):
        return diff_output.decode("utf-8", errors="replace")
    if hasattr(diff_output, "__iter__") and not isinstance(diff_output, str):
        return "\n".join(str(d) for d in diff_output)
    return str(diff_output)
