"""
Index validation for detecting stale indexes (T5).

This module handles:
- Validating the current index against the repository state
- Detecting when the index needs to be rebuilt
- Providing detailed status information about the index
"""
from enum import Enum
from pathlib import Path
from typing import Optional

from .refs import load_refs_snapshot, get_current_refs, compare_refs


class IndexStatus(Enum):
    """
    Status of the index validation.

    Each status has properties:
    - is_valid: Whether the index is safe to use
    - needs_rebuild: Whether the index should be rebuilt
    """
    VALID = ("valid", True, False)
    STALE = ("stale", False, True)
    MISSING_SNAPSHOT = ("missing_snapshot", False, True)
    MISSING_INDEX = ("missing_index", False, True)
    EMPTY_INDEX = ("empty_index", False, True)

    def __init__(self, label: str, is_valid: bool, needs_rebuild: bool):
        self._label = label
        self._is_valid = is_valid
        self._needs_rebuild = needs_rebuild

    @property
    def label(self) -> str:
        """Human-readable label for the status."""
        return self._label

    @property
    def is_valid(self) -> bool:
        """Whether the index is valid and safe to use."""
        return self._is_valid

    @property
    def needs_rebuild(self) -> bool:
        """Whether the index needs to be rebuilt."""
        return self._needs_rebuild


class IndexValidationResult:
    """Result of index validation."""

    def __init__(
        self,
        status: IndexStatus,
        current_refs: Optional[dict] = None,
        snapshot_refs: Optional[dict] = None,
        details: Optional[str] = None
    ):
        self.status = status
        self.current_refs = current_refs or {}
        self.snapshot_refs = snapshot_refs or {}
        self.details = details

    @property
    def is_valid(self) -> bool:
        """Whether the index is valid."""
        return self.status.is_valid

    @property
    def needs_rebuild(self) -> bool:
        """Whether the index needs to be rebuilt."""
        return self.status.needs_rebuild


class IndexValidationError(Exception):
    """Error during index validation."""
    pass


def validate_index(
    repo_root: Path,
    gimi_dir: Optional[Path] = None
) -> IndexValidationResult:
    """
    Validate the current index against the repository state.

    This function checks:
    1. Whether the index directory exists
    2. Whether the refs snapshot exists
    3. Whether the current refs match the snapshot

    Args:
        repo_root: Path to the repository root.
        gimi_dir: Path to the .gimi directory. If None, uses repo_root/.gimi.

    Returns:
        IndexValidationResult containing the validation status.

    Raises:
        IndexValidationError: If validation cannot be performed.
    """
    if gimi_dir is None:
        gimi_dir = repo_root / ".gimi"

    try:
        # Check if index directory exists
        index_dir = gimi_dir / "index"
        if not index_dir.exists():
            return IndexValidationResult(
                status=IndexStatus.MISSING_INDEX,
                details="Index directory does not exist"
            )

        # Check if index directory is empty
        if not any(index_dir.iterdir()):
            return IndexValidationResult(
                status=IndexStatus.EMPTY_INDEX,
                details="Index directory is empty"
            )

        # Load the refs snapshot
        snapshot_refs = load_refs_snapshot(gimi_dir)

        if not snapshot_refs:
            return IndexValidationResult(
                status=IndexStatus.MISSING_SNAPSHOT,
                details="Refs snapshot does not exist or is empty"
            )

        # Get current refs
        try:
            current_refs = get_current_refs(repo_root)
        except Exception as e:
            return IndexValidationResult(
                status=IndexStatus.STALE,
                snapshot_refs=snapshot_refs,
                details=f"Failed to get current refs: {e}"
            )

        # Compare refs
        comparison = compare_refs(snapshot_refs, current_refs)

        if comparison["changed"]:
            return IndexValidationResult(
                status=IndexStatus.STALE,
                current_refs=current_refs,
                snapshot_refs=snapshot_refs,
                details=f"Refs changed: {len(comparison['modified'])} modified, "
                        f"{len(comparison['added'])} added, "
                        f"{len(comparison['removed'])} removed"
            )

        # Index is valid
        return IndexValidationResult(
            status=IndexStatus.VALID,
            current_refs=current_refs,
            snapshot_refs=snapshot_refs,
            details="Index is up to date"
        )

    except Exception as e:
        raise IndexValidationError(f"Failed to validate index: {e}")


def should_rebuild_index(result: IndexValidationResult) -> bool:
    """
    Check if the index should be rebuilt based on validation result.

    Args:
        result: Index validation result.

    Returns:
        True if index should be rebuilt, False otherwise.
    """
    return result.needs_rebuild
