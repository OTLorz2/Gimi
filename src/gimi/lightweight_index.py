"""T7: Lightweight index - commit meta stored for keyword/path retrieval."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from .git_walk import CommitMeta


INDEX_DB = "commits.db"
PATHS_DB = "paths.db"  # optional: path -> commit hashes for path lookup


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS commits (
            hash TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            branch TEXT NOT NULL,
            paths_json TEXT NOT NULL,
            author_time INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commits_branch ON commits(branch)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commits_author_time ON commits(author_time)")
    # FTS5 for keyword search on message (optional; fallback to LIKE)
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS commits_fts USING fts5(
                message, content='commits', content_rowid='rowid'
            )
        """)
    except sqlite3.OperationalError:
        pass  # FTS5 may be disabled
    conn.commit()


def write_commits_batch(conn: sqlite3.Connection, batch: List[CommitMeta]) -> None:
    """Insert or replace a batch of commits into the index."""
    for c in batch:
        paths_json = json.dumps(c.paths, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO commits (hash, message, branch, paths_json, author_time) VALUES (?, ?, ?, ?, ?)",
            (c.hash, c.message, c.branch, paths_json, c.author_time),
        )
    conn.commit()


def open_index(gimi_dir: Path) -> sqlite3.Connection:
    """Open or create the lightweight index DB; caller must close."""
    index_dir = gimi_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(index_dir / INDEX_DB))
    _init_schema(conn)
    return conn


def clear_index(conn: sqlite3.Connection) -> None:
    """Delete all commits (for full rebuild)."""
    conn.execute("DELETE FROM commits")
    conn.commit()


def search_by_keywords(conn: sqlite3.Connection, query: str, limit: int = 100) -> List[str]:
    """Return list of commit hashes where message matches query (LIKE %term%)."""
    terms = [t.strip() for t in query.split() if t.strip()]
    if not terms:
        cur = conn.execute("SELECT hash FROM commits ORDER BY author_time DESC LIMIT ?", (limit,))
        return [row[0] for row in cur.fetchall()]
    placeholders = " OR ".join("message LIKE ?" for _ in terms)
    params = [f"%{t}%" for t in terms] + [limit]
    cur = conn.execute(
        f"SELECT hash FROM commits WHERE {placeholders} ORDER BY author_time DESC LIMIT ?",
        params,
    )
    return [row[0] for row in cur.fetchall()]


def search_by_path(conn: sqlite3.Connection, file_path: str, limit: int = 100) -> List[str]:
    """Return commit hashes that touch this path (exact or prefix)."""
    cur = conn.execute(
        "SELECT hash FROM commits WHERE paths_json LIKE ? ORDER BY author_time DESC LIMIT ?",
        (f"%{file_path}%", limit),
    )
    return [row[0] for row in cur.fetchall()]


def get_commit_meta(conn: sqlite3.Connection, commit_hash: str) -> Optional[CommitMeta]:
    """Fetch one commit meta by hash."""
    cur = conn.execute(
        "SELECT hash, message, branch, paths_json, author_time FROM commits WHERE hash = ?",
        (commit_hash,),
    )
    row = cur.fetchone()
    if not row:
        return None
    paths = json.loads(row[3])
    return CommitMeta(hash=row[0], message=row[1], branch=row[2], paths=paths, author_time=row[4])


def get_all_hashes(conn: sqlite3.Connection) -> List[str]:
    """Return all commit hashes in the index (for vector lookup)."""
    cur = conn.execute("SELECT hash FROM commits")
    return [row[0] for row in cur.fetchall()]
