"""
T5: Index validity checking.

This module handles:
- Validating if the current index is up-to-date
- Comparing current git refs with stored refs snapshots
- Determining if index needs rebuilding or incremental update
"""

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Set, Dict, List

from .config import RefsSnapshot, get_current_refs
from .repo import GimiPaths


class IndexStatus(Enum):
    """Status of the index relative to the repository."""
    VALID = auto()           # Index is up-to-date
    NEEDS_INCREMENTAL = auto()  # Index needs incremental update
    NEEDS_REBUILD = auto()   # Index needs full rebuild
    NOT_FOUND = auto()      # No index exists
    CORRUPT = auto()        # Index appears corrupted


@dataclass
class IndexValidationResult:
    """Result of index validation."""
    status: IndexStatus
    current_refs: RefsSnapshot
    stored_refs: Optional[RefsSnapshot]
    new_branches: Set[str]
    updated_branches: Set[str]
    deleted_branches: Set[str]
    message: str

    @property
    def is_valid(self) -> bool:
        """Check if the index is valid for use."""
        return self.status == IndexStatus.VALID

    @property
    def needs_update(self) -> bool:
        """Check if the index needs any kind of update."""
        return self.status in (IndexStatus.NEEDS_INCREMENTAL,
                               IndexStatus.NEEDS_REBUILD,
                               IndexStatus.NOT_FOUND)


def load_stored_refs(gimi_paths: GimiPaths) -> Optional[RefsSnapshot]:
    """
    Load the stored refs snapshot if it exists.

    Args:
        gimi_paths: GimiPaths instance

    Returns:
        RefsSnapshot if exists, None otherwise
    """
    refs_path = gimi_paths.gimi_dir / 'refs_snapshot.json'
    try:
        if refs_path.exists():
            return RefsSnapshot.load(refs_path)
    except Exception:
        pass
    return None


def save_refs_snapshot(gimi_paths: GimiPaths, refs: RefsSnapshot) -> None:
    """
    Save the refs snapshot to disk.

    Args:
        gimi_paths: GimiPaths instance
        refs: RefsSnapshot to save
    """
    refs_path = gimi_paths.gimi_dir / 'refs_snapshot.json'
    refs.save(refs_path)


def compare_refs(
    current: RefsSnapshot,
    stored: Optional[RefsSnapshot]
) -> Dict[str, any]:
    """
    Compare current refs with stored refs.

    Args:
        current: Current refs snapshot
        stored: Stored refs snapshot (may be None)

    Returns:
        Dictionary with comparison results
    """
    result = {
        'new_branches': set(),
        'updated_branches': set(),
        'deleted_branches': set(),
        'unchanged_branches': set(),
        'has_changes': False,
    }

    if stored is None:
        result['new_branches'] = set(current.branches.keys())
        result['has_changes'] = len(result['new_branches']) > 0
        return result

    current_branches = set(current.branches.keys())
    stored_branches = set(stored.branches.keys())

    result['new_branches'] = current_branches - stored_branches
    result['deleted_branches'] = stored_branches - current_branches

    # Check for updated branches (same branch, different commit)
    common_branches = current_branches & stored_branches
    for branch in common_branches:
        if current.branches[branch] != stored.branches[branch]:
            result['updated_branches'].add(branch)
        else:
            result['unchanged_branches'].add(branch)

    result['has_changes'] = bool(
        result['new_branches'] or
        result['updated_branches'] or
        result['deleted_branches']
    )

    return result


def validate_index(
    gimi_paths: GimiPaths,
    repo_root: Path,
    require_full_index: bool = False
) -> IndexValidationResult:
    """
    Validate the index against the current repository state.

    Args:
        gimi_paths: GimiPaths instance
        repo_root: Repository root path
        require_full_index: If True, only VALID status is acceptable

    Returns:
        IndexValidationResult with status and details
    """
    # Get current git state
    current_refs = get_current_refs(repo_root)

    # Load stored refs if available
    stored_refs = load_stored_refs(gimi_paths)

    # Check if index files exist
    index_exists = (
        gimi_paths.index_dir.exists() and
        any(gimi_paths.index_dir.iterdir())
    )

    # Compare refs
    comparison = compare_refs(current_refs, stored_refs)

    # Determine status
    if not index_exists:
        status = IndexStatus.NOT_FOUND
        message = "No index found. Run 'gimi index' to build the index."
    elif stored_refs is None:
        status = IndexStatus.NEEDS_REBUILD
        message = "No refs snapshot found. Rebuilding index is recommended."
    elif not comparison['has_changes']:
        status = IndexStatus.VALID
        message = "Index is up-to-date."
    else:
        # Determine if we can do incremental or need full rebuild
        # If there are deleted branches or major changes, rebuild
        if comparison['deleted_branches'] and comparison['updated_branches']:
            status = IndexStatus.NEEDS_REBUILD
            message = (
                f"Major repository changes detected: "
                f"{len(comparison['updated_branches'])} branches updated, "
                f"{len(comparison['deleted_branches'])} branches deleted. "
                f"Full rebuild recommended."
            )
        else:
            status = IndexStatus.NEEDS_INCREMENTAL
            message = (
                f"Repository has {len(comparison['new_branches'])} new branches "
                f"and {len(comparison['updated_branches'])} updated branches. "
                f"Incremental update available."
            )

    return IndexValidationResult(
        status=status,
        current_refs=current_refs,
        stored_refs=stored_refs,
        new_branches=comparison['new_branches'],
        updated_branches=comparison['updated_branches'],
        deleted_branches=comparison['deleted_branches'],
        message=message
    )


def mark_index_fresh(gimi_paths: GimiPaths, repo_root: Path) -> None:
    """
    Mark the index as fresh by saving the current refs snapshot.

    Args:
        gimi_paths: GimiPaths instance
        repo_root: Repository root path
    """
    current_refs = get_current_refs(repo_root)
    save_refs_snapshot(gimi_paths, current_refs)


if __name__ == '__main__':
    # Test the validation
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup test environment
        import subprocess
        import os
        os.chdir(tmpdir)

        # Create git repo
        subprocess.run(['git', 'init'], check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], check=True, capture_output=True)

        # Create initial commit
        Path('test.txt').write_text('hello')
        subprocess.run(['git', 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'initial'], check=True, capture_output=True)

        # Now test our code
        from gimi.repo import setup_gimi
        repo_root, paths = setup_gimi()

        # Should be NOT_FOUND since we haven't indexed
        result = validate_index(paths, repo_root)
        print(f"Status: {result.status.name}")
        print(f"Message: {result.message}")
        assert result.status == IndexStatus.NOT_FOUND

        # Simulate having an index by marking it fresh
        mark_index_fresh(paths, repo_root)

        # Now should be VALID
        result = validate_index(paths, repo_root)
        print(f"\nAfter marking fresh:")
        print(f"Status: {result.status.name}")
        print(f"Message: {result.message}")
        assert result.status == IndexStatus.VALID

        print("\nAll validation tests passed!")
