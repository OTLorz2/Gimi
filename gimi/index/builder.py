"""Index builder for traversing git history and building indexes."""

import json
from pathlib import Path
from typing import List, Optional, Iterator, Dict, Any, Callable
from datetime import datetime

from gimi.core.git import (
    CommitMetadata,
    get_commit_metadata,
    get_commit_files,
    get_commits_for_branch,
    get_branches,
    get_current_branch
)
from gimi.core.config import IndexConfig
from gimi.core.refs import capture_refs_snapshot, save_refs_snapshot
from gimi.index.lightweight import LightweightIndex, IndexedCommit


class IndexBuilderError(Exception):
    """Raised when index building fails."""
    pass


class Checkpoint:
    """Checkpoint for incremental index building."""

    def __init__(self, checkpoint_file: Path):
        self.checkpoint_file = checkpoint_file
        self.data: Dict[str, Any] = {}
        if checkpoint_file.exists():
            self.load()

    def load(self) -> None:
        """Load checkpoint from file."""
        try:
            with open(self.checkpoint_file, "r") as f:
                self.data = json.load(f)
        except (json.JSONDecodeError, IOError):
            self.data = {}

    def save(self) -> None:
        """Save checkpoint to file."""
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.checkpoint_file, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from checkpoint."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set value in checkpoint."""
        self.data[key] = value

    def clear(self) -> None:
        """Clear checkpoint data."""
        self.data = {}
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()


class IndexBuilder:
    """Builder for creating and updating the commit index."""

    def __init__(
        self,
        repo_root: Path,
        gimi_dir: Path,
        config: IndexConfig
    ):
        self.repo_root = repo_root
        self.gimi_dir = gimi_dir
        self.config = config
        self.index_dir = gimi_dir / "index"
        self.checkpoint = Checkpoint(gimi_dir / "checkpoint.json")
        self._progress_callback: Optional[Callable[[str, int, int], None]] = None

    def set_progress_callback(
        self,
        callback: Callable[[str, int, int], None]
    ) -> None:
        """
        Set callback for progress updates.

        Args:
            callback: Function called with (message, current, total)
        """
        self._progress_callback = callback

    def _report_progress(self, message: str, current: int, total: int) -> None:
        """Report progress if callback is set."""
        if self._progress_callback:
            self._progress_callback(message, current, total)

    def determine_branches(self) -> List[str]:
        """Determine which branches to index."""
        if self.config.include_all_branches:
            return get_branches(self.repo_root, include_remote=False)

        # Use configured branches
        configured = set(self.config.branches)

        # Add current branch if available
        current = get_current_branch(self.repo_root)
        if current:
            configured.add(current)

        # Filter to only branches that exist
        all_branches = set(get_branches(self.repo_root))
        return list(configured & all_branches)

    def build(self, incremental: bool = True) -> None:
        """
        Build or update the index.

        Args:
            incremental: If True, try to resume from checkpoint
        """
        branches = self.determine_branches()

        if not branches:
            raise IndexBuilderError("No branches to index")

        with LightweightIndex(self.index_dir) as index:
            index.initialize()

            for branch in branches:
                self._index_branch(index, branch, incremental)

        # Save refs snapshot after successful build
        snapshot = capture_refs_snapshot(self.repo_root)
        save_refs_snapshot(snapshot, self.gimi_dir)

        # Clear checkpoint after successful build
        self.checkpoint.clear()

    def _index_branch(
        self,
        index: LightweightIndex,
        branch: str,
        incremental: bool
    ) -> None:
        """Index commits for a single branch."""
        checkpoint_key = f"branch_{branch}"
        last_processed = None

        if incremental:
            last_processed = self.checkpoint.get(checkpoint_key)

        # Get commits to index
        commits = get_commits_for_branch(
            self.repo_root,
            branch,
            max_count=self.config.max_commits,
            after=last_processed
        )

        if not commits:
            return

        # Process in batches
        total = len(commits)
        processed = 0

        for i in range(0, total, self.config.batch_size):
            batch = commits[i:i + self.config.batch_size]
            indexed_commits = []

            for commit_hash in batch:
                meta = get_commit_metadata(self.repo_root, commit_hash)
                if meta:
                    # Get changed files
                    meta.changed_files = get_commit_files(self.repo_root, commit_hash)
                    meta.branches = [branch]
                    indexed_commits.append(
                        IndexedCommit.from_commit_metadata(meta)
                    )

            if indexed_commits:
                index.add_commits(indexed_commits)

            processed += len(batch)
            self._report_progress(
                f"Indexing {branch}",
                processed,
                total
            )

            # Update checkpoint
            self.checkpoint.set(checkpoint_key, batch[-1])
            self.checkpoint.save()

    def get_index(self) -> LightweightIndex:
        """Get the lightweight index."""
        return LightweightIndex(self.index_dir)
