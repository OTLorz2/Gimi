"""Lightweight index for commit metadata."""

import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator
from datetime import datetime

from gimi.core.git import CommitMetadata


class IndexError(Exception):
    """Raised when index operations fail."""
    pass


@dataclass
class IndexedCommit:
    """Commit data as stored in lightweight index."""
    hash: str
    message: str
    author: str
    author_email: str
    author_date: str
    committer: str
    committer_email: str
    committer_date: str
    parents: str  # JSON array
    branches: str  # JSON array
    changed_files: str  # JSON array

    @classmethod
    def from_commit_metadata(cls, meta: CommitMetadata) -> "IndexedCommit":
        """Create IndexedCommit from CommitMetadata."""
        return cls(
            hash=meta.hash,
            message=meta.message,
            author=meta.author,
            author_email=meta.author_email,
            author_date=meta.author_date,
            committer=meta.committer,
            committer_email=meta.committer_email,
            committer_date=meta.committer_date,
            parents=json.dumps(meta.parents),
            branches=json.dumps(meta.branches),
            changed_files=json.dumps(meta.changed_files)
        )

    def to_commit_metadata(self) -> CommitMetadata:
        """Convert to CommitMetadata."""
        return CommitMetadata(
            hash=self.hash,
            message=self.message,
            author=self.author,
            author_email=self.author_email,
            author_date=self.author_date,
            committer=self.committer,
            committer_email=self.committer_email,
            committer_date=self.committer_date,
            parents=json.loads(self.parents),
            branches=json.loads(self.branches),
            changed_files=json.loads(self.changed_files)
        )


class LightweightIndex:
    """SQLite-based lightweight index for commit metadata."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS commits (
        hash TEXT PRIMARY KEY,
        message TEXT NOT NULL,
        author TEXT NOT NULL,
        author_email TEXT NOT NULL,
        author_date TEXT NOT NULL,
        committer TEXT NOT NULL,
        committer_email TEXT NOT NULL,
        committer_date TEXT NOT NULL,
        parents TEXT NOT NULL DEFAULT '[]',
        branches TEXT NOT NULL DEFAULT '[]',
        changed_files TEXT NOT NULL DEFAULT '[]'
    );

    CREATE INDEX IF NOT EXISTS idx_author ON commits(author);
    CREATE INDEX IF NOT EXISTS idx_author_date ON commits(author_date);
    CREATE VIRTUAL TABLE IF NOT EXISTS commits_fts USING fts5(
        hash,
        message,
        author,
        content='commits',
        content_rowid='rowid'
    );

    CREATE INDEX IF NOT EXISTS idx_branches ON commits(branches);
    """

    def __init__(self, index_dir: Path):
        """
        Initialize lightweight index.

        Args:
            index_dir: Path to index directory (e.g., .gimi/index)
        """
        self.index_dir = index_dir
        self.db_path = index_dir / "commits.db"
        self._conn: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False

    def add_commit(self, commit: IndexedCommit) -> None:
        """
        Add or update a commit in the index.

        Args:
            commit: Commit data to add
        """
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO commits
            (hash, message, author, author_email, author_date,
             committer, committer_email, committer_date,
             parents, branches, changed_files)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                commit.hash, commit.message, commit.author,
                commit.author_email, commit.author_date,
                commit.committer, commit.committer_email,
                commit.committer_date, commit.parents,
                commit.branches, commit.changed_files
            )
        )
        conn.commit()

    def add_commits(self, commits: List[IndexedCommit]) -> None:
        """
        Add multiple commits in a batch.

        Args:
            commits: List of commits to add
        """
        conn = self._get_connection()
        conn.execute("BEGIN TRANSACTION")
        try:
            for commit in commits:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO commits
                    (hash, message, author, author_email, author_date,
                     committer, committer_email, committer_date,
                     parents, branches, changed_files)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        commit.hash, commit.message, commit.author,
                        commit.author_email, commit.author_date,
                        commit.committer, commit.committer_email,
                        commit.committer_date, commit.parents,
                        commit.branches, commit.changed_files
                    )
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_commit(self, commit_hash: str) -> Optional[IndexedCommit]:
        """
        Get a commit by hash.

        Args:
            commit_hash: Commit hash

        Returns:
            IndexedCommit or None if not found
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM commits WHERE hash = ?",
            (commit_hash,)
        ).fetchone()

        if row is None:
            return None

        return IndexedCommit(
            hash=row["hash"],
            message=row["message"],
            author=row["author"],
            author_email=row["author_email"],
            author_date=row["author_date"],
            committer=row["committer"],
            committer_email=row["committer_email"],
            committer_date=row["committer_date"],
            parents=row["parents"],
            branches=row["branches"],
            changed_files=row["changed_files"]
        )

    def search_by_message(self, query: str, limit: int = 100) -> List[IndexedCommit]:
        """
        Search commits by message content.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching commits
        """
        conn = self._get_connection()
        # Simple LIKE-based search for now
        # Could be enhanced with FTS5
        pattern = f"%{query}%"
        rows = conn.execute(
            """
            SELECT * FROM commits
            WHERE message LIKE ? OR author LIKE ?
            ORDER BY author_date DESC
            LIMIT ?
            """,
            (pattern, pattern, limit)
        ).fetchall()

        return [
            IndexedCommit(
                hash=row["hash"],
                message=row["message"],
                author=row["author"],
                author_email=row["author_email"],
                author_date=row["author_date"],
                committer=row["committer"],
                committer_email=row["committer_email"],
                committer_date=row["committer_date"],
                parents=row["parents"],
                branches=row["branches"],
                changed_files=row["changed_files"]
            )
            for row in rows
        ]

    def search_by_path(self, path_pattern: str, limit: int = 100) -> List[IndexedCommit]:
        """
        Search commits that touched files matching path pattern.

        Args:
            path_pattern: Path pattern (substring match)
            limit: Maximum results

        Returns:
            List of matching commits
        """
        conn = self._get_connection()
        pattern = f"%{path_pattern}%"
        rows = conn.execute(
            """
            SELECT * FROM commits
            WHERE changed_files LIKE ?
            ORDER BY author_date DESC
            LIMIT ?
            """,
            (pattern, limit)
        ).fetchall()

        return [
            IndexedCommit(
                hash=row["hash"],
                message=row["message"],
                author=row["author"],
                author_email=row["author_email"],
                author_date=row["author_date"],
                committer=row["committer"],
                committer_email=row["committer_email"],
                committer_date=row["committer_date"],
                parents=row["parents"],
                branches=row["branches"],
                changed_files=row["changed_files"]
            )
            for row in rows
        ]

    def get_all_commits(self, limit: Optional[int] = None) -> List[IndexedCommit]:
        """
        Get all indexed commits.

        Args:
            limit: Maximum number of commits

        Returns:
            List of all commits
        """
        conn = self._get_connection()

        if limit:
            rows = conn.execute(
                "SELECT * FROM commits ORDER BY author_date DESC LIMIT ?",
                (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM commits ORDER BY author_date DESC"
            ).fetchall()

        return [
            IndexedCommit(
                hash=row["hash"],
                message=row["message"],
                author=row["author"],
                author_email=row["author_email"],
                author_date=row["author_date"],
                committer=row["committer"],
                committer_email=row["committer_email"],
                committer_date=row["committer_date"],
                parents=row["parents"],
                branches=row["branches"],
                changed_files=row["changed_files"]
            )
            for row in rows
        ]

    def count(self) -> int:
        """Get total number of commits in index."""
        conn = self._get_connection()
        row = conn.execute("SELECT COUNT(*) FROM commits").fetchone()
        return row[0] if row else 0

    def clear(self) -> None:
        """Clear all commits from index."""
        conn = self._get_connection()
        conn.execute("DELETE FROM commits")
        conn.commit()
