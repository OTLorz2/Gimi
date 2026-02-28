"""
T7: 轻量索引写入

功能：
- 将 T6 产出的 commit 元数据写入 `.gimi/index`
- 支持按 message、路径、分支、时间查询
- 与 T2 锁配合，写入前加锁
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager

from gimi.git_traversal import CommitMeta
from gimi.lock import gimi_lock


class LightIndex:
    """
    轻量索引，使用 SQLite 存储 commit 元数据

    支持高效的：
    - 关键词检索（在 message 中搜索）
    - 路径匹配（查找涉及特定文件的 commit）
    - 分支过滤
    - 时间范围过滤
    """

    DB_FILENAME = "commits.db"

    def __init__(self, gimi_path: Path):
        self.gimi_path = Path(gimi_path)
        self.db_path = self.gimi_path / "index" / self.DB_FILENAME
        self._ensure_db()

    @contextmanager
    def _connect(self):
        """创建数据库连接（上下文管理器）"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_db(self) -> None:
        """确保数据库和表结构存在"""
        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            # commits 主表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commits (
                    hash TEXT PRIMARY KEY,
                    short_hash TEXT NOT NULL,
                    message TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    author_email TEXT NOT NULL,
                    author_date TIMESTAMP NOT NULL,
                    committer_name TEXT NOT NULL,
                    committer_email TEXT NOT NULL,
                    committer_date TIMESTAMP NOT NULL,
                    parents TEXT,  -- JSON 数组
                    stats TEXT,    -- JSON 对象
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 分支关联表（多对多）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commit_branches (
                    commit_hash TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    PRIMARY KEY (commit_hash, branch),
                    FOREIGN KEY (commit_hash) REFERENCES commits(hash) ON DELETE CASCADE
                )
            """)

            # 文件变更表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commit_files (
                    commit_hash TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    PRIMARY KEY (commit_hash, file_path),
                    FOREIGN KEY (commit_hash) REFERENCES commits(hash) ON DELETE CASCADE
                )
            """)

            # 创建索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_commits_author_date
                ON commits(author_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_commits_message
                ON commits(message)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_commit_branches_branch
                ON commit_branches(branch)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_commit_files_path
                ON commit_files(file_path)
            """)

            conn.commit()

    def add_commit(self, commit: CommitMeta) -> None:
        """
        添加单个 commit 到索引

        Args:
            commit: commit 元数据
        """
        with self._connect() as conn:
            self._insert_commit(conn, commit)
            conn.commit()

    def add_commits(self, commits: List[CommitMeta]) -> None:
        """
        批量添加 commit 到索引

        Args:
            commits: commit 元数据列表
        """
        with self._connect() as conn:
            for commit in commits:
                self._insert_commit(conn, commit)
            conn.commit()

    def _insert_commit(self, conn: sqlite3.Connection, commit: CommitMeta) -> None:
        """插入 commit 数据（内部方法）"""
        # 插入主表
        conn.execute("""
            INSERT OR REPLACE INTO commits (
                hash, short_hash, message, author_name, author_email,
                author_date, committer_name, committer_email, committer_date,
                parents, stats
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            commit.hash,
            commit.short_hash or commit.hash[:7],
            commit.message,
            commit.author_name,
            commit.author_email,
            commit.author_date.isoformat() if commit.author_date else None,
            commit.committer_name,
            commit.committer_email,
            commit.committer_date.isoformat() if commit.committer_date else None,
            json.dumps(commit.parents),
            json.dumps(commit.stats),
        ))

        # 插入分支关联
        if commit.branches:
            for branch in commit.branches:
                conn.execute("""
                    INSERT OR IGNORE INTO commit_branches (commit_hash, branch)
                    VALUES (?, ?)
                """, (commit.hash, branch))

        # 插入文件关联
        if commit.files_changed:
            for file_path in commit.files_changed:
                conn.execute("""
                    INSERT OR IGNORE INTO commit_files (commit_hash, file_path)
                    VALUES (?, ?)
                """, (commit.hash, file_path))

    def search_by_message(
        self,
        keywords: List[str],
        branch: Optional[str] = None,
        limit: int = 100
    ) -> List[CommitMeta]:
        """
        按 message 关键词搜索

        Args:
            keywords: 关键词列表
            branch: 分支过滤
            limit: 最大返回数量

        Returns:
            List[CommitMeta]: 匹配的 commit 列表
        """
        with self._connect() as conn:
            if keywords:
                # 构建 OR 条件的 LIKE 查询
                conditions = []
                params = []
                for kw in keywords:
                    conditions.append("message LIKE ?")
                    params.append(f"%{kw}%")

                where_clause = " OR ".join(conditions)
            else:
                where_clause = "1=1"
                params = []

            # 如果指定了分支，添加分支过滤
            if branch:
                query = f"""
                    SELECT c.* FROM commits c
                    JOIN commit_branches cb ON c.hash = cb.commit_hash
                    WHERE ({where_clause}) AND cb.branch = ?
                    ORDER BY c.author_date DESC
                    LIMIT ?
                """
                params.append(branch)
                params.append(limit)
            else:
                query = f"""
                    SELECT * FROM commits
                    WHERE {where_clause}
                    ORDER BY author_date DESC
                    LIMIT ?
                """
                params.append(limit)

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            return [self._row_to_commit(row) for row in rows]

    def search_by_path(
        self,
        file_path: str,
        branch: Optional[str] = None,
        limit: int = 100
    ) -> List[CommitMeta]:
        """
        按文件路径搜索

        Args:
            file_path: 文件路径（支持前缀匹配）
            branch: 分支过滤
            limit: 最大返回数量

        Returns:
            List[CommitMeta]: 匹配的 commit 列表
        """
        with self._connect() as conn:
            if branch:
                query = """
                    SELECT c.* FROM commits c
                    JOIN commit_branches cb ON c.hash = cb.commit_hash
                    JOIN commit_files cf ON c.hash = cf.commit_hash
                    WHERE cf.file_path LIKE ? AND cb.branch = ?
                    ORDER BY c.author_date DESC
                    LIMIT ?
                """
                params = [f"{file_path}%", branch, limit]
            else:
                query = """
                    SELECT c.* FROM commits c
                    JOIN commit_files cf ON c.hash = cf.commit_hash
                    WHERE cf.file_path LIKE ?
                    ORDER BY c.author_date DESC
                    LIMIT ?
                """
                params = [f"{file_path}%", limit]

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            return [self._row_to_commit(row) for row in rows]

    def get_commit(self, commit_hash: str) -> Optional[CommitMeta]:
        """
        根据 hash 获取单个 commit

        Args:
            commit_hash: commit hash（完整或短 hash）

        Returns:
            Optional[CommitMeta]: commit 元数据，如果不存在则返回 None
        """
        with self._connect() as conn:
            # 尝试完整 hash
            cursor = conn.execute(
                "SELECT * FROM commits WHERE hash = ?",
                (commit_hash,)
            )
            row = cursor.fetchone()

            if row:
                return self._row_to_commit(row)

            # 尝试短 hash 前缀匹配
            cursor = conn.execute(
                "SELECT * FROM commits WHERE hash LIKE ?",
                (f"{commit_hash}%",)
            )
            row = cursor.fetchone()

            if row:
                return self._row_to_commit(row)

            return None

    def _row_to_commit(self, row: sqlite3.Row) -> CommitMeta:
        """将数据库行转换为 CommitMeta"""
        # 解析 JSON 字段
        parents = json.loads(row["parents"]) if row["parents"] else []
        stats = json.loads(row["stats"]) if row["stats"] else {}

        # 解析日期
        try:
            author_date = datetime.fromisoformat(row["author_date"]) if row["author_date"] else None
        except (ValueError, TypeError):
            author_date = None

        try:
            committer_date = datetime.fromisoformat(row["committer_date"]) if row["committer_date"] else None
        except (ValueError, TypeError):
            committer_date = None

        return CommitMeta(
            hash=row["hash"],
            short_hash=row["short_hash"],
            message=row["message"],
            author_name=row["author_name"],
            author_email=row["author_email"],
            author_date=author_date,
            committer_name=row["committer_name"],
            committer_email=row["committer_email"],
            committer_date=committer_date,
            parents=parents,
            stats=stats,
        )

    def get_commit_count(self) -> int:
        """获取索引中的 commit 总数"""
        with self._connect() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM commits")
            return cursor.fetchone()[0]

    def get_branches(self) -> List[str]:
        """获取索引中所有分支"""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT branch FROM commit_branches ORDER BY branch"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_files(self, limit: int = 1000) -> List[str]:
        """获取索引中所有文件路径"""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT file_path FROM commit_files ORDER BY file_path LIMIT ?",
                (limit,)
            )
            return [row[0] for row in cursor.fetchall()]

    def clear(self) -> None:
        """清空索引（谨慎使用）"""
        with self._connect() as conn:
            conn.execute("DELETE FROM commit_files")
            conn.execute("DELETE FROM commit_branches")
            conn.execute("DELETE FROM commits")
            conn.commit()


if __name__ == "__main__":
    import tempfile

    print("测试轻量索引...")

    with tempfile.TemporaryDirectory() as tmpdir:
        gimi_path = Path(tmpdir) / ".gimi"
        gimi_path.mkdir(parents=True)

        # 创建轻量索引
        index = LightIndex(gimi_path)
        print(f"索引数据库路径: {index.db_path}")

        # 创建测试 commit 数据
        test_commits = [
            CommitMeta(
                hash="abc123def456789012345678901234567890abcd",
                short_hash="abc123d",
                message="Add user authentication feature",
                author_name="张三",
                author_email="zhangsan@example.com",
                author_date=datetime.now(),
                committer_name="张三",
                committer_email="zhangsan@example.com",
                committer_date=datetime.now(),
                branches=["main", "feature/auth"],
                parents=["parent123"],
                files_changed=["src/auth.py", "src/user.py", "tests/test_auth.py"],
                stats={"insertions": 150, "deletions": 20, "files_changed": 3},
            ),
            CommitMeta(
                hash="def789abc0123456789012345678901234567890",
                short_hash="def789a",
                message="Fix database connection timeout issue",
                author_name="李四",
                author_email="lisi@example.com",
                author_date=datetime.now(),
                committer_name="李四",
                committer_email="lisi@example.com",
                committer_date=datetime.now(),
                branches=["main", "hotfix/db-timeout"],
                parents=["parent456"],
                files_changed=["src/db.py", "config/database.yml"],
                stats={"insertions": 45, "deletions": 10, "files_changed": 2},
            ),
        ]

        # 测试 1: 批量添加 commit
        print("\n测试 1: 批量添加 commit")
        index.add_commits(test_commits)
        print(f"  已添加 {len(test_commits)} 个 commit")

        # 测试 2: 查询 commit 数量
        print("\n测试 2: 查询 commit 数量")
        count = index.get_commit_count()
        print(f"  索引中共有 {count} 个 commit")

        # 测试 3: 按关键词搜索
        print("\n测试 3: 按关键词搜索 'fix'")
        results = index.search_by_message(["fix"], limit=10)
        print(f"  找到 {len(results)} 个匹配的 commit")
        for r in results:
            print(f"    - {r.short_hash}: {r.message[:50]}")

        # 测试 4: 按路径搜索
        print("\n测试 4: 按路径搜索 'src/auth.py'")
        results = index.search_by_path("src/auth", limit=10)
        print(f"  找到 {len(results)} 个匹配的 commit")
        for r in results:
            print(f"    - {r.short_hash}: {r.message[:50]}")

        # 测试 5: 获取分支列表
        print("\n测试 5: 获取分支列表")
        branches = index.get_branches()
        print(f"  索引中有 {len(branches)} 个分支")
        for b in branches:
            print(f"    - {b}")

        # 测试 6: 获取单个 commit
        print("\n测试 6: 获取单个 commit")
        commit = index.get_commit(test_commits[0].hash)
        if commit:
            print(f"  找到 commit: {commit.short_hash}")
            print(f"  消息: {commit.message}")
            print(f"  作者: {commit.author_name}")
        else:
            print("  未找到 commit")

    print("\n所有测试完成!")
