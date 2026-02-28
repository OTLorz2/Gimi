"""Diff retrieval and truncation for commit context."""

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
import json


class DiffError(Exception):
    """Raised when diff operations fail."""
    pass


@dataclass
class TruncationConfig:
    """Configuration for diff truncation."""
    max_files_per_commit: int = 10
    max_lines_per_file: int = 50
    max_total_lines: int = 500
    max_diff_size_bytes: int = 100 * 1024  # 100KB

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "max_files_per_commit": self.max_files_per_commit,
            "max_lines_per_file": self.max_lines_per_file,
            "max_total_lines": self.max_total_lines,
            "max_diff_size_bytes": self.max_diff_size_bytes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TruncationConfig":
        """Create from dictionary."""
        return cls(
            max_files_per_commit=data.get("max_files_per_commit", 10),
            max_lines_per_file=data.get("max_lines_per_file", 50),
            max_total_lines=data.get("max_total_lines", 500),
            max_diff_size_bytes=data.get("max_diff_size_bytes", 100 * 1024)
        )


@dataclass
class FileDiff:
    """Diff for a single file."""
    old_path: str
    new_path: str
    status: str  # added, deleted, modified, renamed
    diff_text: str
    additions: int = 0
    deletions: int = 0
    is_truncated: bool = False

    @property
    def path(self) -> str:
        """Get the file path (old or new)."""
        return self.new_path if self.new_path else self.old_path


@dataclass
class DiffResult:
    """Result of fetching and truncating a commit diff."""
    commit_hash: str
    commit_message: str
    author: str
    author_date: str
    files: List[FileDiff]
    total_additions: int = 0
    total_deletions: int = 0
    is_truncated: bool = False
    truncation_reason: Optional[str] = None

    def to_text(self) -> str:
        """Convert diff result to text for LLM context."""
        lines = [
            f"Commit: {self.commit_hash}",
            f"Author: {self.author} <{self.author_date}>",
            f"Message: {self.commit_message}",
            f"Files changed: {len(self.files)}",
            "---"
        ]

        for file_diff in self.files:
            lines.append(f"\nFile: {file_diff.path} ({file_diff.status})")
            lines.append(f"+{file_diff.additions}/-{file_diff.deletions}")
            lines.append(file_diff.diff_text)
            lines.append("---")

        if self.is_truncated:
            lines.append(f"\n[Note: Diff was truncated: {self.truncation_reason}]")

        return "\n".join(lines)

    def estimate_tokens(self) -> int:
        """Estimate token count (rough heuristic)."""
        text = self.to_text()
        # Rough estimate: ~4 characters per token on average
        return len(text) // 4


class DiffManager:
    """Manager for retrieving and truncating commit diffs."""

    def __init__(
        self,
        repo_root: Path,
        cache_dir: Optional[Path] = None,
        config: Optional[TruncationConfig] = None
    ):
        """
        Initialize diff manager.

        Args:
            repo_root: Path to repository root
            cache_dir: Optional directory for caching diffs
            config: Truncation configuration
        """
        self.repo_root = repo_root
        self.cache_dir = cache_dir
        self.config = config or TruncationConfig()

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, commit_hash: str) -> Optional[Path]:
        """Get cache file path for a commit."""
        if not self.cache_dir:
            return None
        # Use first 2 chars of hash as subdir for distribution
        subdir = self.cache_dir / commit_hash[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{commit_hash}.json"

    def _load_from_cache(self, commit_hash: str) -> Optional[DiffResult]:
        """Load diff result from cache."""
        cache_path = self._get_cache_path(commit_hash)
        if not cache_path or not cache_path.exists():
            return None

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._deserialize_diff_result(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def _save_to_cache(self, commit_hash: str, result: DiffResult) -> None:
        """Save diff result to cache."""
        cache_path = self._get_cache_path(commit_hash)
        if not cache_path:
            return

        try:
            data = self._serialize_diff_result(result)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except (IOError, TypeError):
            pass

    def _serialize_diff_result(self, result: DiffResult) -> Dict[str, Any]:
        """Serialize DiffResult to dictionary."""
        return {
            "commit_hash": result.commit_hash,
            "commit_message": result.commit_message,
            "author": result.author,
            "author_date": result.author_date,
            "files": [
                {
                    "old_path": f.old_path,
                    "new_path": f.new_path,
                    "status": f.status,
                    "diff_text": f.diff_text,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "is_truncated": f.is_truncated
                }
                for f in result.files
            ],
            "total_additions": result.total_additions,
            "total_deletions": result.total_deletions,
            "is_truncated": result.is_truncated,
            "truncation_reason": result.truncation_reason
        }

    def _deserialize_diff_result(self, data: Dict[str, Any]) -> DiffResult:
        """Deserialize DiffResult from dictionary."""
        return DiffResult(
            commit_hash=data["commit_hash"],
            commit_message=data["commit_message"],
            author=data["author"],
            author_date=data["author_date"],
            files=[
                FileDiff(
                    old_path=f["old_path"],
                    new_path=f["new_path"],
                    status=f["status"],
                    diff_text=f["diff_text"],
                    additions=f["additions"],
                    deletions=f["deletions"],
                    is_truncated=f["is_truncated"]
                )
                for f in data["files"]
            ],
            total_additions=data["total_additions"],
            total_deletions=data["total_deletions"],
            is_truncated=data["is_truncated"],
            truncation_reason=data.get("truncation_reason")
        )

    def get_diff(
        self,
        commit_hash: str,
        commit_message: str = "",
        author: str = "",
        author_date: str = ""
    ) -> DiffResult:
        """
        Get diff for a commit with caching and truncation.

        Args:
            commit_hash: Commit hash
            commit_message: Commit message (for metadata)
            author: Author name
            author_date: Author date

        Returns:
            DiffResult with truncated diff
        """
        # Try cache first
        cached = self._load_from_cache(commit_hash)
        if cached:
            return cached

        # Fetch from git
        try:
            result = self._fetch_diff_from_git(
                commit_hash, commit_message, author, author_date
            )

            # Save to cache
            self._save_to_cache(commit_hash, result)

            return result
        except DiffError:
            # Return empty result on error
            return DiffResult(
                commit_hash=commit_hash,
                commit_message=commit_message,
                author=author,
                author_date=author_date,
                files=[],
                is_truncated=True,
                truncation_reason="Failed to fetch diff"
            )

    def _fetch_diff_from_git(
        self,
        commit_hash: str,
        commit_message: str,
        author: str,
        author_date: str
    ) -> DiffResult:
        """Fetch and truncate diff from git."""
        try:
            # First, get the diff stat to see what files changed
            stat_result = subprocess.run(
                ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", commit_hash],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=True
            )

            file_changes = []
            for line in stat_result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    status = parts[0][0]  # First char
                    file_path = parts[1]
                    old_path = parts[2] if len(parts) > 2 else file_path

                    status_map = {
                        "A": "added",
                        "D": "deleted",
                        "M": "modified",
                        "R": "renamed",
                        "T": "type_changed"
                    }
                    file_changes.append((
                        status_map.get(status, "modified"),
                        file_path,
                        old_path
                    ))

        except subprocess.CalledProcessError as e:
            raise DiffError(f"Failed to get diff stat: {e}")

        # Truncate files if needed
        total_additions = 0
        total_deletions = 0
        files = []
        is_truncated = False
        truncation_reason = None

        if len(file_changes) > self.config.max_files_per_commit:
            file_changes = file_changes[:self.config.max_files_per_commit]
            is_truncated = True
            truncation_reason = f"Limited to {self.config.max_files_per_commit} files"

        for status, file_path, old_path in file_changes:
            try:
                # Get diff for this file
                diff_result = subprocess.run(
                    ["git", "show", "--no-color", "--format="
                     "-p", commit_hash, "--", file_path],
                    cwd=str(self.repo_root),
                    capture_output=True,
                    text=True,
                    check=True
                )

                diff_text = diff_result.stdout

                # Parse additions/deletions from diff
                additions = diff_text.count("\n+") - diff_text.count("\n+++")
                deletions = diff_text.count("\n-") - diff_text.count("\n---")
                additions = max(0, additions)
                deletions = max(0, deletions)

                # Truncate lines if needed
                file_truncated = False
                lines = diff_text.split("\n")
                if len(lines) > self.config.max_lines_per_file:
                    lines = lines[:self.config.max_lines_per_file]
                    lines.append(f"\n... ({len(diff_text.split(chr(10))) - self.config.max_lines_per_file} more lines)")
                    diff_text = "\n".join(lines)
                    file_truncated = True

                total_additions += additions
                total_deletions += deletions

                files.append(FileDiff(
                    old_path=old_path,
                    new_path=file_path,
                    status=status,
                    diff_text=diff_text,
                    additions=additions,
                    deletions=deletions,
                    is_truncated=file_truncated
                ))

            except subprocess.CalledProcessError:
                # Skip files that can't be fetched
                continue

        # Check total line limit
        total_lines = sum(len(f.diff_text.split("\n")) for f in files)
        if total_lines > self.config.max_total_lines:
            # Remove files until under limit
            while files and total_lines > self.config.max_total_lines:
                removed = files.pop()
                total_lines -= len(removed.diff_text.split("\n"))
            is_truncated = True
            truncation_reason = f"Limited to {self.config.max_total_lines} total lines"

        return DiffResult(
            commit_hash=commit_hash,
            commit_message=commit_message,
            author=author,
            author_date=author_date,
            files=files,
            total_additions=total_additions,
            total_deletions=total_deletions,
            is_truncated=is_truncated,
            truncation_reason=truncation_reason
        )

    def clear_cache(self) -> None:
        """Clear the diff cache."""
        if not self.cache_dir or not self.cache_dir.exists():
            return

        import shutil
        for item in self.cache_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                try:
                    item.unlink()
                except IOError:
                    pass
