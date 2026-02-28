"""
Refs snapshot handling for index validation (T4, T5).

This module handles:
- Saving and loading refs snapshots
- Getting current refs from git
- Comparing refs to detect changes
"""
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class RefsError(Exception):
    """Error related to refs operations."""
    pass


def run_git_command(
    args: List[str],
    cwd: Optional[Path] = None,
    check: bool = True
) -> Tuple[int, str, str]:
    """
    Run a git command and return the result.

    Args:
        args: List of command arguments (not including 'git').
        cwd: Working directory for the command.
        check: Whether to raise an exception on non-zero exit.

    Returns:
        Tuple of (returncode, stdout, stderr).

    Raises:
        RefsError: If the command fails and check=True.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )

        if check and result.returncode != 0:
            raise RefsError(f"Git command failed: {result.stderr}")

        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        if check:
            raise RefsError(f"Failed to run git command: {e}")
        return -1, "", str(e)


def get_refs_snapshot_path(gimi_dir: Path) -> Path:
    """
    Get the path to the refs snapshot file.

    Args:
        gimi_dir: Path to the .gimi directory.

    Returns:
        Path to the refs snapshot file.
    """
    return gimi_dir / "refs_snapshot.json"


def load_refs_snapshot(gimi_dir: Path) -> Dict[str, str]:
    """
    Load the refs snapshot from disk.

    Args:
        gimi_dir: Path to the .gimi directory.

    Returns:
        Dictionary mapping branch names to commit hashes.
        Returns empty dict if snapshot doesn't exist.

    Raises:
        RefsError: If snapshot file exists but is invalid.
    """
    snapshot_path = get_refs_snapshot_path(gimi_dir)

    if not snapshot_path.exists():
        return {}

    try:
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise RefsError(f"Invalid JSON in refs snapshot: {e}")
    except Exception as e:
        raise RefsError(f"Failed to load refs snapshot: {e}")


def save_refs_snapshot(gimi_dir: Path, refs: Dict[str, str]) -> None:
    """
    Save the refs snapshot to disk.

    Args:
        gimi_dir: Path to the .gimi directory.
        refs: Dictionary mapping branch names to commit hashes.

    Raises:
        RefsError: If unable to save snapshot.
    """
    snapshot_path = get_refs_snapshot_path(gimi_dir)

    try:
        # Ensure parent directory exists
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)

        with open(snapshot_path, 'w', encoding='utf-8') as f:
            json.dump(refs, f, indent=2, sort_keys=True)
    except Exception as e:
        raise RefsError(f"Failed to save refs snapshot: {e}")


def get_current_refs(repo_root: Path) -> Dict[str, str]:
    """
    Get the current refs from the git repository.

    Returns refs for all local branches.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Dictionary mapping branch names to commit hashes.

    Raises:
        RefsError: If unable to get current refs.
    """
    try:
        # Use run_git_command for better testability
        rc, stdout, stderr = run_git_command(
            ["for-each-ref", "--format=%(objectname) %(refname:short)", "refs/heads/"],
            cwd=repo_root,
            check=False
        )

        if rc != 0:
            raise RefsError(f"Failed to get current refs: {stderr}")

        refs = {}
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if line:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    commit_hash, ref_name = parts
                    refs[ref_name] = commit_hash

        return refs
    except RefsError:
        raise
    except Exception as e:
        raise RefsError(f"Failed to get current refs: {e}")


def compare_refs(
    old_refs: Dict[str, str],
    new_refs: Dict[str, str]
) -> Dict[str, any]:
    """
    Compare two refs snapshots and detect changes.

    Args:
        old_refs: Previous refs snapshot.
        new_refs: Current refs snapshot.

    Returns:
        Dictionary containing:
        - changed: True if any changes detected
        - added: List of branch names that were added
        - removed: List of branch names that were removed
        - modified: List of branch names with changed commit hash
    """
    old_keys = set(old_refs.keys())
    new_keys = set(new_refs.keys())

    added = list(new_keys - old_keys)
    removed = list(old_keys - new_keys)

    # Check for modified refs (same branch, different commit)
    common_keys = old_keys & new_keys
    modified = [
        key for key in common_keys
        if old_refs[key] != new_refs[key]
    ]

    changed = bool(added or removed or modified)

    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "modified": modified
    }


def are_refs_consistent(old_refs: Dict[str, str], new_refs: Dict[str, str]) -> bool:
    """
    Check if two refs snapshots are consistent (unchanged).

    Args:
        old_refs: Previous refs snapshot.
        new_refs: Current refs snapshot.

    Returns:
        True if refs are consistent (no changes), False otherwise.
    """
    result = compare_refs(old_refs, new_refs)
    return not result["changed"]


def capture_refs_snapshot(repo_root: Path) -> Dict[str, str]:
    """
    Capture the current refs snapshot from the git repository.

    This is an alias for get_current_refs() to provide a more descriptive
    name for the operation of capturing a snapshot.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Dictionary mapping branch names to commit hashes.
    """
    return get_current_refs(repo_root)
