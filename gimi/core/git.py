"""Git operations for commit traversal and metadata extraction."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Iterator, Dict, Any
from datetime import datetime


class GitError(Exception):
    """Raised when git operations fail."""
    pass


@dataclass
class CommitMetadata:
    """Metadata for a single commit."""
    hash: str
    message: str
    author: str
    author_email: str
    author_date: str
    committer: str
    committer_email: str
    committer_date: str
    parents: List[str] = field(default_factory=list)
    branches: List[str] = field(default_factory=list)
    changed_files: List[str] = field(default_factory=list)

    @property
    def short_hash(self) -> str:
        """Get short commit hash (7 characters)."""
        return self.hash[:7]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hash": self.hash,
            "message": self.message,
            "author": self.author,
            "author_email": self.author_email,
            "author_date": self.author_date,
            "committer": self.committer,
            "committer_email": self.committer_email,
            "committer_date": self.committer_date,
            "parents": self.parents,
            "branches": self.branches,
            "changed_files": self.changed_files
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommitMetadata":
        """Create from dictionary."""
        return cls(
            hash=data["hash"],
            message=data["message"],
            author=data.get("author", ""),
            author_email=data.get("author_email", ""),
            author_date=data.get("author_date", ""),
            committer=data.get("committer", ""),
            committer_email=data.get("committer_email", ""),
            committer_date=data.get("committer_date", ""),
            parents=data.get("parents", []),
            branches=data.get("branches", []),
            changed_files=data.get("changed_files", [])
        )


def get_current_branch(repo_root: Path) -> Optional[str]:
    """Get current branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )
        branch = result.stdout.strip()
        return None if branch == "HEAD" else branch
    except subprocess.CalledProcessError:
        return None


def get_branches(repo_root: Path, include_remote: bool = False) -> List[str]:
    """Get list of branches."""
    try:
        cmd = ["git", "branch", "-a"] if include_remote else ["git", "branch"]
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )

        branches = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("* "):
                line = line[2:]
            if line.startswith("remotes/"):
                line = line[8:]  # Remove remotes/
            if line and line not in branches:
                branches.append(line)

        return branches
    except subprocess.CalledProcessError:
        return []


def get_commits_for_branch(
    repo_root: Path,
    branch: str,
    max_count: Optional[int] = None,
    since: Optional[str] = None,
    after: Optional[str] = None
) -> List[str]:
    """
    Get list of commit hashes for a branch.

    Args:
        repo_root: Path to repository root
        branch: Branch name
        max_count: Maximum number of commits
        since: Only commits after this date (ISO format)
        after: Only commits after this commit hash

    Returns:
        List of commit hashes
    """
    cmd = ["git", "log", branch, "--format=%H"]

    if max_count:
        cmd.extend(["--max-count", str(max_count)])

    if since:
        cmd.extend(["--since", since])

    if after:
        cmd.extend([f"{after}..{branch}"])

    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )

        commits = [h.strip() for h in result.stdout.strip().split("\n") if h.strip()]
        return commits
    except subprocess.CalledProcessError:
        return []


def get_commit_metadata(repo_root: Path, commit_hash: str) -> Optional[CommitMetadata]:
    """
    Get metadata for a single commit.

    Args:
        repo_root: Path to repository root
        commit_hash: Commit hash

    Returns:
        CommitMetadata or None if commit not found
    """
    # Use git log to get commit info
    format_str = (
        "%H%n"  # hash
        "%an%n"  # author name
        "%ae%n"  # author email
        "%ai%n"  # author date
        "%cn%n"  # committer name
        "%ce%n"  # committer email
        "%ci%n"  # committer date
        "%P%n"  # parent hashes
        "%B%x00"  # message (ends with null)
    )

    try:
        result = subprocess.run(
            ["git", "log", "-1", f"--format={format_str}", commit_hash],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError:
        return None

    parts = result.stdout.split("\x00", 1)
    if len(parts) != 2:
        return None

    header, message = parts
    lines = header.strip().split("\n")

    # Need at least 9 lines (for initial commits without parents)
    # 10 lines for normal commits (with parent hashes on line 7)
    if len(lines) < 9:
        return None

    return CommitMetadata(
        hash=lines[0],
        author=lines[1],
        author_email=lines[2],
        author_date=lines[3],
        committer=lines[4],
        committer_email=lines[5],
        committer_date=lines[6],
        parents=lines[7].split() if lines[7] else [],
        message=message.strip()
    )


def get_commit_files(repo_root: Path, commit_hash: str) -> List[str]:
    """
    Get list of files changed in a commit.

    Args:
        repo_root: Path to repository root
        commit_hash: Commit hash

    Returns:
        List of changed file paths
    """
    try:
        # Try git show --name-only which works for all commits including initial commits
        result = subprocess.run(
            ["git", "show", "--name-only", "--format=", commit_hash],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )

        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except subprocess.CalledProcessError:
        # Fallback to diff-tree for older git versions
        try:
            result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=True
            )
            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            return files
        except subprocess.CalledProcessError:
            return []
        return []


def get_commit_diff(repo_root: Path, commit_hash: str, max_lines: Optional[int] = None) -> str:
    """
    Get diff for a commit.

    Args:
        repo_root: Path to repository root
        commit_hash: Commit hash
        max_lines: Maximum number of lines to return

    Returns:
        Diff as string
    """
    try:
        result = subprocess.run(
            ["git", "show", "--patch", "--no-color", commit_hash],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True
        )

        diff = result.stdout

        if max_lines and max_lines > 0:
            lines = diff.split("\n")
            diff = "\n".join(lines[:max_lines])

        return diff
    except subprocess.CalledProcessError:
        return ""
