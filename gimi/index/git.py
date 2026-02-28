"""
T6: Git traversal and commit metadata extraction.

This module handles:
- Traversing git history for specified branches
- Extracting structured metadata for each commit
- Supporting filtering by branch, count, and date
- Batching for large repositories
"""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple
import json


@dataclass
class CommitMetadata:
    """
    Structured metadata for a single commit.

    This is a lightweight representation without the full diff.
    """
    hash: str
    short_hash: str = ""
    message: str = ""
    author_name: str = ""
    author_email: str = ""
    author_timestamp: int = 0
    committer_name: str = ""
    committer_email: str = ""
    committer_timestamp: int = 0
    branches: List[str] = field(default_factory=list)
    parent_hashes: List[str] = field(default_factory=list)
    files_changed: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)  # additions, deletions, files

    def __post_init__(self):
        if not self.short_hash and self.hash:
            self.short_hash = self.hash[:7]

    @property
    def author_date(self) -> datetime:
        """Get author date as datetime object."""
        return datetime.fromtimestamp(self.author_timestamp)

    @property
    def committer_date(self) -> datetime:
        """Get committer date as datetime object."""
        return datetime.fromtimestamp(self.committer_timestamp)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'hash': self.hash,
            'short_hash': self.short_hash,
            'message': self.message,
            'author_name': self.author_name,
            'author_email': self.author_email,
            'author_timestamp': self.author_timestamp,
            'committer_name': self.committer_name,
            'committer_email': self.committer_email,
            'committer_timestamp': self.committer_timestamp,
            'branches': self.branches,
            'parent_hashes': self.parent_hashes,
            'files_changed': self.files_changed,
            'stats': self.stats,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CommitMetadata':
        """Create from dictionary."""
        return cls(
            hash=data['hash'],
            short_hash=data.get('short_hash', ''),
            message=data.get('message', ''),
            author_name=data.get('author_name', ''),
            author_email=data.get('author_email', ''),
            author_timestamp=data.get('author_timestamp', 0),
            committer_name=data.get('committer_name', ''),
            committer_email=data.get('committer_email', ''),
            committer_timestamp=data.get('committer_timestamp', 0),
            branches=data.get('branches', []),
            parent_hashes=data.get('parent_hashes', []),
            files_changed=data.get('files_changed', []),
            stats=data.get('stats', {}),
        )


class GitTraversalError(Exception):
    """Error during git traversal."""
    pass


class GitTraversal:
    """
    Traverses git history and extracts commit metadata.

    Supports:
    - Branch filtering
    - Commit count limits
    - Date range filtering
    - Batch processing
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self._branches: Optional[List[str]] = None

    def _run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the repository."""
        result = subprocess.run(
            ['git'] + args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False
        )
        if check and result.returncode != 0:
            raise GitTraversalError(
                f"Git command failed: git {' '.join(args)}\n"
                f"Error: {result.stderr}"
            )
        return result

    def get_branches(self, remote: bool = False) -> List[str]:
        """Get list of branches in the repository."""
        args = ['branch', '--format=%(refname:short)']
        if remote:
            args.append('-a')

        result = self._run_git(args)
        branches = [b.strip() for b in result.stdout.strip().split('\n') if b.strip()]
        return branches

    def traverse_commits(
        self,
        branches: Optional[List[str]] = None,
        max_commits: int = 0,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        batch_size: int = 100,
    ) -> Iterator[CommitMetadata]:
        """
        Traverse commits and yield metadata.

        Args:
            branches: List of branches to traverse (None = all branches)
            max_commits: Maximum commits to yield (0 = unlimited)
            since: Only yield commits after this date
            until: Only yield commits before this date
            batch_size: Number of commits to fetch per batch

        Yields:
            CommitMetadata for each commit
        """
        if branches is None:
            branches = self.get_branches()

        count = 0
        seen_hashes: Set[str] = set()

        for branch in branches:
            if max_commits > 0 and count >= max_commits:
                break

            # Build git log command
            args = [
                'log',
                branch,
                f'--format=%H|%an|%ae|%at|%cn|%ce|%ct|%P|%s',
                '--numstat',
                '--no-decorate'
            ]

            if since:
                args.append(f'--since={since.isoformat()}')
            if until:
                args.append(f'--until={until.isoformat()}')
            if batch_size > 0:
                args.append(f'--max-count={batch_size}')

            try:
                result = self._run_git(args, check=False)
                if result.returncode != 0:
                    continue

                commits = self._parse_log_output(result.stdout)

                for commit in commits:
                    if commit.hash in seen_hashes:
                        continue

                    seen_hashes.add(commit.hash)
                    commit.branches = [branch]

                    yield commit

                    count += 1
                    if max_commits > 0 and count >= max_commits:
                        return

            except GitTraversalError:
                continue

    def _parse_log_output(self, output: str) -> List[CommitMetadata]:
        """Parse git log output into CommitMetadata objects."""
        commits = []
        lines = output.strip().split('\n')

        i = 0
        while i < len(lines):
            line = lines[i]
            if not line or '|' not in line:
                i += 1
                continue

            # Parse commit line: hash|author|email|timestamp|...
            parts = line.split('|', 8)  # Split into 9 parts
            if len(parts) < 9:
                i += 1
                continue

            commit = CommitMetadata(
                hash=parts[0],
                author_name=parts[1],
                author_email=parts[2],
                author_timestamp=int(parts[3]) if parts[3].isdigit() else 0,
                committer_name=parts[4],
                committer_email=parts[5],
                committer_timestamp=int(parts[6]) if parts[6].isdigit() else 0,
                parent_hashes=parts[7].split() if parts[7] else [],
                message=parts[8],
            )

            # Parse numstat lines until next commit or end
            i += 1
            additions = 0
            deletions = 0
            files = []

            while i < len(lines):
                stat_line = lines[i]
                if not stat_line or stat_line.startswith('<'):
                    i += 1
                    continue
                # Check if this is a new commit
                if '|' in stat_line and len(stat_line.split('|', 1)[0]) == 40:
                    break
                # Parse numstat line: additions\tdeletions\tpath
                stat_parts = stat_line.split('\t')
                if len(stat_parts) >= 3:
                    try:
                        add = int(stat_parts[0]) if stat_parts[0] != '-' else 0
                        delete = int(stat_parts[1]) if stat_parts[1] != '-' else 0
                        path = stat_parts[2]
                        additions += add
                        deletions += delete
                        files.append(path)
                    except ValueError:
                        pass
                i += 1

            commit.stats = {
                'additions': additions,
                'deletions': deletions,
                'files': len(files)
            }
            commit.files_changed = files
            commits.append(commit)

        return commits


if __name__ == '__main__':
    # Test the git traversal
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup test repo
        import subprocess
        repo_dir = Path(tmpdir) / "test_repo"
        repo_dir.mkdir()

        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True, capture_output=True)

        # Create some commits
        for i in range(5):
            (repo_dir / f"file{i}.txt").write_text(f"content {i}")
            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"Commit {i}"], cwd=repo_dir, check=True, capture_output=True)

        # Test traversal
        print("Testing GitTraversal...")
        traversal = GitTraversal(repo_dir)

        branches = traversal.get_branches()
        print(f"Found branches: {branches}")

        commit_count = 0
        for commit in traversal.traverse_commits(max_commits=10):
            print(f"  Commit: {commit.short_hash} - {commit.message[:50]}")
            print(f"    Author: {commit.author_name}")
            print(f"    Files: {len(commit.files_changed)}")
            print(f"    Stats: +{commit.stats.get('additions', 0)}/-{commit.stats.get('deletions', 0)}")
            commit_count += 1

        print(f"\nTotal commits traversed: {commit_count}")
        print("\nGitTraversal test completed successfully!")
