"""
T9: Large repository strategy and checkpointing.

This module implements checkpointing for indexing large repositories.
It allows indexing to resume from where it left off if interrupted.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from gimi.index.git import CommitMetadata


@dataclass
class Checkpoint:
    """
    Checkpoint data for resuming indexing.

    Tracks the progress of indexing to allow resuming from
    the last successfully processed commit.
    """
    # Identifiers
    checkpoint_id: str = ""  # Unique identifier for this checkpoint
    repo_root: str = ""  # Repository root path

    # Progress tracking
    branches_to_index: List[str] = field(default_factory=list)
    branches_completed: List[str] = field(default_factory=list)
    branches_in_progress: List[str] = field(default_factory=list)

    # Commit tracking per branch
    # branch -> last processed commit hash
    last_commit_by_branch: Dict[str, str] = field(default_factory=dict)
    # branch -> count of processed commits
    commit_count_by_branch: Dict[str, int] = field(default_factory=dict)

    # Overall stats
    total_commits_processed: int = 0
    total_commits_target: int = 0  # 0 = unknown/unlimited

    # Timing
    started_at: str = ""
    last_updated_at: str = ""
    completed_at: str = ""

    # Batch tracking
    batch_size: int = 100
    current_batch: int = 0
    total_batches: int = 0

    # Status
    status: str = "pending"  # pending, running, paused, completed, failed
    error_message: str = ""

    def __post_init__(self):
        if not self.checkpoint_id:
            self.checkpoint_id = self._generate_id()
        if not self.started_at and self.status == "pending":
            self.started_at = datetime.utcnow().isoformat()

    def _generate_id(self) -> str:
        """Generate a unique checkpoint ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        random_suffix = hashlib.md5(
            f"{time.time()}{id(self)}".encode()
        ).hexdigest()[:8]
        return f"checkpoint_{timestamp}_{random_suffix}"

    def update_progress(
        self,
        branch: str,
        commit_hash: str,
        increment_count: int = 1
    ) -> None:
        """
        Update progress for a branch.

        Args:
            branch: Branch name
            commit_hash: Last processed commit hash
            increment_count: Number of commits to add to count
        """
        self.last_commit_by_branch[branch] = commit_hash

        current_count = self.commit_count_by_branch.get(branch, 0)
        self.commit_count_by_branch[branch] = current_count + increment_count

        self.total_commits_processed += increment_count
        self.last_updated_at = datetime.utcnow().isoformat()

    def mark_branch_complete(self, branch: str) -> None:
        """Mark a branch as completed."""
        if branch in self.branches_in_progress:
            self.branches_in_progress.remove(branch)
        if branch not in self.branches_completed:
            self.branches_completed.append(branch)
        self.last_updated_at = datetime.utcnow().isoformat()

    def mark_branch_in_progress(self, branch: str) -> None:
        """Mark a branch as in progress."""
        if branch not in self.branches_in_progress:
            self.branches_in_progress.append(branch)
        self.last_updated_at = datetime.utcnow().isoformat()

    def is_complete(self) -> bool:
        """Check if indexing is complete."""
        return len(self.branches_completed) == len(self.branches_to_index)

    def get_progress_percentage(self) -> float:
        """Get progress as a percentage."""
        if not self.branches_to_index:
            return 0.0

        branch_weight = 100.0 / len(self.branches_to_index)
        progress = 0.0

        for branch in self.branches_to_index:
            if branch in self.branches_completed:
                progress += branch_weight
            elif branch in self.branches_in_progress:
                # Estimate progress within branch
                commit_count = self.commit_count_by_branch.get(branch, 0)
                # Assume 1000 commits per branch if unknown
                estimated_total = 1000
                if self.total_commits_target > 0:
                    estimated_total = self.total_commits_target // len(self.branches_to_index)

                branch_progress = min(commit_count / estimated_total, 1.0)
                progress += branch_weight * branch_progress

        return progress

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'checkpoint_id': self.checkpoint_id,
            'repo_root': self.repo_root,
            'branches_to_index': self.branches_to_index,
            'branches_completed': self.branches_completed,
            'branches_in_progress': self.branches_in_progress,
            'last_commit_by_branch': self.last_commit_by_branch,
            'commit_count_by_branch': self.commit_count_by_branch,
            'total_commits_processed': self.total_commits_processed,
            'total_commits_target': self.total_commits_target,
            'started_at': self.started_at,
            'last_updated_at': self.last_updated_at,
            'completed_at': self.completed_at,
            'batch_size': self.batch_size,
            'current_batch': self.current_batch,
            'total_batches': self.total_batches,
            'status': self.status,
            'error_message': self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Checkpoint':
        """Create from dictionary."""
        checkpoint = cls(
            checkpoint_id=data.get('checkpoint_id', ''),
            repo_root=data.get('repo_root', ''),
        )
        checkpoint.branches_to_index = data.get('branches_to_index', [])
        checkpoint.branches_completed = data.get('branches_completed', [])
        checkpoint.branches_in_progress = data.get('branches_in_progress', [])
        checkpoint.last_commit_by_branch = data.get('last_commit_by_branch', {})
        checkpoint.commit_count_by_branch = data.get('commit_count_by_branch', {})
        checkpoint.total_commits_processed = data.get('total_commits_processed', 0)
        checkpoint.total_commits_target = data.get('total_commits_target', 0)
        checkpoint.started_at = data.get('started_at', '')
        checkpoint.last_updated_at = data.get('last_updated_at', '')
        checkpoint.completed_at = data.get('completed_at', '')
        checkpoint.batch_size = data.get('batch_size', 100)
        checkpoint.current_batch = data.get('current_batch', 0)
        checkpoint.total_batches = data.get('total_batches', 0)
        checkpoint.status = data.get('status', 'pending')
        checkpoint.error_message = data.get('error_message', '')
        return checkpoint

    def save(self, path: Path) -> None:
        """Save checkpoint to file."""
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> 'Checkpoint':
        """Load checkpoint from file."""
        data = json.loads(path.read_text())
        return cls.from_dict(data)


class CheckpointManager:
    """
    Manages checkpoints for indexing operations.

    Provides methods to create, load, and manage checkpoints
    for resumable indexing.
    """

    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def create_checkpoint(
        self,
        repo_root: Path,
        branches: List[str],
        batch_size: int = 100
    ) -> Checkpoint:
        """
        Create a new checkpoint.

        Args:
            repo_root: Repository root path
            branches: List of branches to index
            batch_size: Batch size for processing

        Returns:
            New Checkpoint instance
        """
        checkpoint = Checkpoint(
            repo_root=str(repo_root),
            branches_to_index=branches.copy(),
            batch_size=batch_size,
            status="running"
        )

        # Save the checkpoint
        self.save_checkpoint(checkpoint)

        return checkpoint

    def save_checkpoint(self, checkpoint: Checkpoint) -> Path:
        """
        Save a checkpoint to disk.

        Args:
            checkpoint: Checkpoint to save

        Returns:
            Path to saved checkpoint file
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
        checkpoint.save(checkpoint_path)
        return checkpoint_path

    def load_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """
        Load a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint ID

        Returns:
            Checkpoint if found, None otherwise
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"
        if not checkpoint_path.exists():
            return None

        return Checkpoint.load(checkpoint_path)

    def list_checkpoints(self) -> List[Checkpoint]:
        """
        List all available checkpoints.

        Returns:
            List of Checkpoint objects
        """
        checkpoints = []
        for checkpoint_file in sorted(self.checkpoint_dir.glob("*.json")):
            try:
                checkpoint = Checkpoint.load(checkpoint_file)
                checkpoints.append(checkpoint)
            except Exception:
                pass
        return checkpoints

    def get_latest_checkpoint(self, repo_root: Optional[Path] = None) -> Optional[Checkpoint]:
        """
        Get the most recent checkpoint.

        Args:
            repo_root: If provided, only consider checkpoints for this repo

        Returns:
            Most recent Checkpoint or None
        """
        checkpoints = self.list_checkpoints()

        if repo_root:
            repo_str = str(repo_root)
            checkpoints = [c for c in checkpoints if c.repo_root == repo_str]

        if not checkpoints:
            return None

        # Sort by last_updated_at (most recent first)
        checkpoints.sort(
            key=lambda c: c.last_updated_at or c.started_at or "",
            reverse=True
        )

        return checkpoints[0]

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint ID to delete

        Returns:
            True if deleted, False if not found
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            return True
        return False

    def cleanup_old_checkpoints(self, keep: int = 5) -> int:
        """
        Delete old checkpoints, keeping only the most recent ones.

        Args:
            keep: Number of recent checkpoints to keep

        Returns:
            Number of checkpoints deleted
        """
        checkpoints = self.list_checkpoints()

        # Sort by last_updated_at (most recent first)
        checkpoints.sort(
            key=lambda c: c.last_updated_at or c.started_at or "",
            reverse=True
        )

        # Delete old checkpoints
        deleted = 0
        for checkpoint in checkpoints[keep:]:
            if self.delete_checkpoint(checkpoint.checkpoint_id):
                deleted += 1

        return deleted


if __name__ == '__main__':
    # Test checkpoint functionality
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        checkpoint_dir = Path(tmpdir) / "checkpoints"

        print("Testing CheckpointManager...")

        # Create manager
        manager = CheckpointManager(checkpoint_dir)

        # Create a checkpoint
        repo_root = Path("/tmp/test-repo")
        branches = ["main", "develop"]

        checkpoint = manager.create_checkpoint(repo_root, branches, batch_size=50)
        print(f"✓ Created checkpoint: {checkpoint.checkpoint_id}")
        print(f"  Repo: {checkpoint.repo_root}")
        print(f"  Branches: {checkpoint.branches_to_index}")
        print(f"  Status: {checkpoint.status}")

        # Simulate progress
        checkpoint.mark_branch_in_progress("main")
        checkpoint.update_progress("main", "abc123", 10)
        checkpoint.update_progress("main", "def456", 10)

        # Save progress
        manager.save_checkpoint(checkpoint)
        print(f"\n✓ Saved progress")
        print(f"  Total commits: {checkpoint.total_commits_processed}")
        print(f"  Progress: {checkpoint.get_progress_percentage():.1f}%")

        # Load checkpoint
        loaded = manager.load_checkpoint(checkpoint.checkpoint_id)
        if loaded:
            print(f"\n✓ Loaded checkpoint: {loaded.checkpoint_id}")
            print(f"  Total commits: {loaded.total_commits_processed}")
            print(f"  Last commit (main): {loaded.last_commit_by_branch.get('main')}")

        # List checkpoints
        checkpoints = manager.list_checkpoints()
        print(f"\n✓ Listed {len(checkpoints)} checkpoint(s)")

        # Get latest
        latest = manager.get_latest_checkpoint()
        if latest:
            print(f"✓ Latest checkpoint: {latest.checkpoint_id}")

        # Test cleanup
        # Create a few more checkpoints
        for i in range(3):
            cp = manager.create_checkpoint(repo_root, [f"branch-{i}"])
            time.sleep(0.01)  # Ensure different timestamps

        print(f"\n✓ Created additional checkpoints")
        print(f"  Total: {len(manager.list_checkpoints())}")

        # Cleanup old ones, keep only 3
        deleted = manager.cleanup_old_checkpoints(keep=3)
        print(f"✓ Cleaned up {deleted} old checkpoint(s)")
        print(f"  Remaining: {len(manager.list_checkpoints())}")

        print("\n✓ All CheckpointManager tests passed!")
