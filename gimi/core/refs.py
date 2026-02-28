"""Refs snapshot management for index validity tracking."""

import json
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


class RefsError(Exception):
    """Raised when refs operations fail."""
    pass


@dataclass
class RefsSnapshot:
    """
    Snapshot of repository refs at a point in time.

    This is used to track whether the index is up-to-date with the
    current repository state.
    """
    # Map of ref name (e.g., "refs/heads/main") to commit hash
    refs: Dict[str, str] = field(default_factory=dict)

    # Current HEAD
    head: Optional[str] = None

    # When the snapshot was created
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Optional: commit counts per branch for quick validation
    commit_counts: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RefsSnapshot":
        """Create snapshot from dictionary."""
        return cls(
            refs=data.get("refs", {}),
            head=data.get("head"),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            commit_counts=data.get("commit_counts", {})
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert snapshot to dictionary."""
        return asdict(self)

    def diff(self, other: "RefsSnapshot") -> Dict[str, Any]:
        """
        Compare this snapshot with another.

        Returns a dict describing the differences:
        - changed_refs: dict of ref -> (old_hash, new_hash)
        - new_refs: set of new ref names
        - removed_refs: set of removed ref names
        - head_changed: whether HEAD changed
        """
        self_refs = set(self.refs.keys())
        other_refs = set(other.refs.keys())

        new_refs = other_refs - self_refs
        removed_refs = self_refs - other_refs
        common_refs = self_refs & other_refs

        changed_refs = {}
        for ref in common_refs:
            if self.refs[ref] != other.refs[ref]:
                changed_refs[ref] = (self.refs[ref], other.refs[ref])

        return {
            "changed_refs": changed_refs,
            "new_refs": new_refs,
            "removed_refs": removed_refs,
            "head_changed": self.head != other.head,
            "head_old": self.head,
            "head_new": other.head
        }


def get_snapshot_path(gimi_dir: Path) -> Path:
    """Get path to refs snapshot file."""
    return gimi_dir / "refs_snapshot.json"


def capture_refs_snapshot(repo_root: Path) -> RefsSnapshot:
    """
    Capture current refs state of the repository.

    Args:
        repo_root: Path to repository root

    Returns:
        Snapshot of current refs state

    Raises:
        RefsError: If refs cannot be read
    """
    snapshot = RefsSnapshot()

    try:
        # Get current HEAD
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )
        snapshot.head = result.stdout.strip()
    except subprocess.CalledProcessError:
        # Might be a fresh repo with no commits
        snapshot.head = None

    # Get all refs
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname) %(objectname)"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )

        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    ref_name = parts[0]
                    commit_hash = parts[1]
                    snapshot.refs[ref_name] = commit_hash

    except subprocess.CalledProcessError as e:
        raise RefsError(f"Failed to read refs: {e}")

    return snapshot


def load_refs_snapshot(gimi_dir: Path) -> Optional[RefsSnapshot]:
    """
    Load saved refs snapshot.

    Args:
        gimi_dir: Path to .gimi directory

    Returns:
        Loaded snapshot or None if not exists

    Raises:
        RefsError: If snapshot exists but cannot be loaded
    """
    snapshot_path = get_snapshot_path(gimi_dir)

    if not snapshot_path.exists():
        return None

    try:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RefsSnapshot.from_dict(data)
    except json.JSONDecodeError as e:
        raise RefsError(f"Invalid snapshot JSON: {e}")
    except Exception as e:
        raise RefsError(f"Failed to load snapshot: {e}")


def save_refs_snapshot(snapshot: RefsSnapshot, gimi_dir: Path) -> None:
    """
    Save refs snapshot.

    Args:
        snapshot: Snapshot to save
        gimi_dir: Path to .gimi directory

    Raises:
        RefsError: If snapshot cannot be saved
    """
    snapshot_path = get_snapshot_path(gimi_dir)

    try:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, indent=2)
    except Exception as e:
        raise RefsError(f"Failed to save snapshot: {e}")


def get_current_refs(repo_root: Path) -> RefsSnapshot:
    """
    Get current refs state of the repository.

    This is an alias for capture_refs_snapshot for API consistency.

    Args:
        repo_root: Path to repository root

    Returns:
        Current refs snapshot
    """
    return capture_refs_snapshot(repo_root)


def are_refs_consistent(saved: RefsSnapshot, current: RefsSnapshot) -> bool:
    """
    Check if saved refs snapshot is consistent with current state.

    Args:
        saved: Saved refs snapshot
        current: Current refs snapshot

    Returns:
        True if refs are consistent (no changes detected)
    """
    if not saved or not current:
        return False

    diff = saved.diff(current)

    # Consider consistent if no changes in refs or HEAD
    return (
        not diff["changed_refs"] and
        not diff["new_refs"] and
        not diff["removed_refs"] and
        not diff["head_changed"]
    )


def check_index_validity(
    gimi_dir: Path,
    repo_root: Path
) -> tuple[bool, Optional[RefsSnapshot], Optional[RefsSnapshot]]:
    """
    Check if the current index is valid (up-to-date with repo).

    Args:
        gimi_dir: Path to .gimi directory
        repo_root: Path to repository root

    Returns:
        Tuple of (is_valid, current_snapshot, saved_snapshot):
        - is_valid: True if index is up-to-date
        - current_snapshot: Current refs state (or None on error)
        - saved_snapshot: Last saved snapshot (or None if not exists)
    """
    # Get current state
    try:
        current = capture_refs_snapshot(repo_root)
    except RefsError:
        return False, None, None

    # Get saved state
    try:
        saved = load_refs_snapshot(gimi_dir)
    except RefsError:
        return False, current, None

    if saved is None:
        # No saved snapshot means index needs to be built
        return False, current, None

    # Compare refs
    # For now, we consider the index invalid if any refs changed
    # This could be made more sophisticated (e.g., only check indexed branches)
    diff = saved.diff(current)

    is_valid = (
        not diff["changed_refs"] and
        not diff["new_refs"] and
        not diff["removed_refs"] and
        not diff["head_changed"]
    )

    return is_valid, current, saved
