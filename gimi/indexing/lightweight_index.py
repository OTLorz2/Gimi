"""
轻量索引实现
使用SQLite存储commit元数据，支持关键词和路径检索
"""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Iterator, Dict, Any

from gimi.indexing.git_collector import CommitMetadata


@dataclass
class IndexEntry:
    """索引条目"""

    commit_hash: str
    message: str
    author: str
    author_email: str
    timestamp: int
    branch: str
    changed_files: str  # JSON array
    insertions: int
    deletions: int
    parent_hashes: str  # JSON array

    @classmethod
    def from_commit(cls, commit: CommitMetadata) -> "IndexEntry":
        """从CommitMetadata创建"""
        return cls(
            commit_hash=commit.hash,
            message=commit.message,
            author=commit.author,
            author_email=commit.author_email,
            timestamp=commit.timestamp,
            branch=commit.branch,
            changed_files=json.dumps(commit.changed_files),
            insertions=commit.insertions,
            deletions=commit.deletions,
            parent_hashes=json.dumps(commit.parent_hashes),
        )

    def to_commit(self) -> CommitMetadata:
        """转换为CommitMetadata"""
        return CommitMetadata(
            hash=self.commit_hash,
            message=self.message,
            author=self.author,
            author_email=self.author_email,
            timestamp=self.timestamp,
            branch=self.branch,
            changed_files=json.loads(self.changed_files),
            insertions=self.insertions,
            deletions=self.deletions,
            parent_hashes=json.loads(self.parent_hashes),
        )


class LightweightIndex:
    """
    轻量索引

    使用SQLite存储commit元数据，支持:
    - 按关键词搜索commit message
    - 按路径搜索commit
    - 按作者、时间、分支筛选
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS commits (
        commit_hash TEXT PRIMARY KEY,
        message TEXT NOT NULL,
        author TEXT NOT NULL,
        author_email TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        branch TEXT NOT NULL,
        changed_files TEXT NOT NULL,  -- JSON array
        insertions INTEGER DEFAULT 0,
        deletions INTEGER DEFAULT 0,
        parent_hashes TEXT  -- JSON array
    );

    -- 全文搜索索引
    CREATE VIRTUAL TABLE IF NOT EXISTS commits_fts USING fts5(
        commit_hash UNINDEXED,
        message,
        content='commits',
        content_rowid='rowid'
    );

    -- 触发器：保持FTS索引同步
    CREATE TRIGGER IF NOT EXISTS commits_ai AFTER INSERT ON commits BEGIN
        INSERT INTO commits_fts(rowid, message)
        VALUES (new.rowid, new.message);
    END;

    CREATE TRIGGER IF NOT EXISTS commits_ad AFTER DELETE ON commits BEGIN
        INSERT INTO commits_fts(commits_fts, rowid, message)
        VALUES ('delete', old.rowid, old.message);
    END;

    CREATE TRIGGER IF NOT EXISTS commits_au AFTER UPDATE ON commits BEGIN
        INSERT INTO commits_fts(commits_fts, rowid, message)
        VALUES ('delete', old.rowid, old.message);
        INSERT INTO commits_fts(rowid, message)
        VALUES (new.rowid, new.message);
    END;

    -- 辅助索引
    CREATE INDEX IF NOT EXISTS idx_author ON commits(author);
    CREATE INDEX IF NOT EXISTS idx_timestamp ON commits(timestamp);
    CREATE INDEX IF NOT EXISTS idx_branch ON commits(branch);
    """

    def __init__(self, db_path: Path):
        """
        初始化轻量索引

        Args:
            db_path: SQLite数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize_schema(self) -> None:
        """初始化数据库schema"""
        conn = self._get_connection()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False

    def add_commit(self, commit: CommitMetadata) -> None:
        """
        添加单个commit到索引

        Args:
            commit: Commit元数据
        """
        entry = IndexEntry.from_commit(commit)
        conn = self._get_connection()

        conn.execute(
            """
            INSERT OR REPLACE INTO commits
            (commit_hash, message, author, author_email, timestamp, branch,
             changed_files, insertions, deletions, parent_hashes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.commit_hash,
                entry.message,
                entry.author,
                entry.author_email,
                entry.timestamp,
                entry.branch,
                entry.changed_files,
                entry.insertions,
                entry.deletions,
                entry.parent_hashes,
            ),
        )
        conn.commit()

    def add_commits_batch(self, commits: List[CommitMetadata]) -> None:
        """
        批量添加commits到索引

        Args:
            commits: Commit元数据列表
        """
        entries = [IndexEntry.from_commit(c) for c in commits]
        conn = self._get_connection()

        data = [
            (
                e.commit_hash,
                e.message,
                e.author,
                e.author_email,
                e.timestamp,
                e.branch,
                e.changed_files,
                e.insertions,
                e.deletions,
                e.parent_hashes,
            )
            for e in entries
        ]

        conn.executemany(
            """
            INSERT OR REPLACE INTO commits
            (commit_hash, message, author, author_email, timestamp, branch,
             changed_files, insertions, deletions, parent_hashes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )
        conn.commit()

    def search_by_keyword(
        self,
        query: str,
        limit: int = 100,
    ) -> List[CommitMetadata]:
        """
        使用关键词搜索commit message

        Args:
            query: 搜索关键词
            limit: 最大返回数量

        Returns:
            匹配的commit列表
        """
        conn = self._get_connection()

        # 使用FTS5进行全文搜索
        cursor = conn.execute(
            """
            SELECT c.* FROM commits c
            JOIN commits_fts fts ON c.rowid = fts.rowid
            WHERE commits_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit),
        )

        results = []
        for row in cursor.fetchall():
            entry = IndexEntry(
                commit_hash=row["commit_hash"],
                message=row["message"],
                author=row["author"],
                author_email=row["author_email"],
                timestamp=row["timestamp"],
                branch=row["branch"],
                changed_files=row["changed_files"],
                insertions=row["insertions"],
                deletions=row["deletions"],
                parent_hashes=row["parent_hashes"],
            )
            results.append(entry.to_commit())

        return results

    def search_by_path(
        self,
        file_path: str,
        limit: int = 100,
    ) -> List[CommitMetadata]:
        """
        使用文件路径搜索commit

        Args:
            file_path: 文件路径（支持前缀匹配）
            limit: 最大返回数量

        Returns:
            匹配的commit列表
        """
        conn = self._get_connection()

        # 使用LIKE进行前缀匹配
        pattern = f"%{file_path}%"

        cursor = conn.execute(
            """
            SELECT * FROM commits
            WHERE changed_files LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (pattern, limit),
        )

        results = []
        for row in cursor.fetchall():
            entry = IndexEntry(
                commit_hash=row["commit_hash"],
                message=row["message"],
                author=row["author"],
                author_email=row["author_email"],
                timestamp=row["timestamp"],
                branch=row["branch"],
                changed_files=row["changed_files"],
                insertions=row["insertions"],
                deletions=row["deletions"],
                parent_hashes=row["parent_hashes"],
            )
            results.append(entry.to_commit())

        return results

    def get_commit_by_hash(self, commit_hash: str) -> Optional[CommitMetadata]:
        """通过hash获取commit"""
        conn = self._get_connection()

        cursor = conn.execute(
            "SELECT * FROM commits WHERE commit_hash = ?",
            (commit_hash,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        entry = IndexEntry(
            commit_hash=row["commit_hash"],
            message=row["message"],
            author=row["author"],
            author_email=row["author_email"],
            timestamp=row["timestamp"],
            branch=row["branch"],
            changed_files=row["changed_files"],
            insertions=row["insertions"],
            deletions=row["deletions"],
            parent_hashes=row["parent_hashes"],
        )
        return entry.to_commit()

    def get_stats(self) -> dict:
        """获取索引统计信息"""
        conn = self._get_connection()

        stats = {
            "total_commits": 0,
            "branches": set(),
            "authors": set(),
            "date_range": {"earliest": None, "latest": None},
        }

        cursor = conn.execute("SELECT COUNT(*) FROM commits")
        stats["total_commits"] = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT DISTINCT branch, author, timestamp FROM commits"
        )
        for row in cursor.fetchall():
            stats["branches"].add(row["branch"])
            stats["authors"].add(row["author"])

            ts = row["timestamp"]
            if stats["date_range"]["earliest"] is None or ts < stats["date_range"]["earliest"]:
                stats["date_range"]["earliest"] = ts
            if stats["date_range"]["latest"] is None or ts > stats["date_range"]["latest"]:
                stats["date_range"]["latest"] = ts

        # 转换set为list以便JSON序列化
        stats["branches"] = sorted(list(stats["branches"]))
        stats["authors"] = sorted(list(stats["authors"]))

        return stats

    def clear(self) -> None:
        """清空所有索引数据"""
        conn = self._get_connection()
        conn.execute("DELETE FROM commits")
        conn.commit()
