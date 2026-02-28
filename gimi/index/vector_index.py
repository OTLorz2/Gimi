"""Vector index for semantic search over commits."""

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import sqlite3


class VectorIndexError(Exception):
    """Raised when vector index operations fail."""
    pass


@dataclass
class VectorCommit:
    """Commit with its embedding vector."""
    hash: str
    message: str
    changed_files: str  # JSON array
    embedding: bytes  # Binary vector data

    @classmethod
    def create_embedding_input(cls, message: str, changed_files: List[str]) -> str:
        """Create the text input for embedding generation."""
        files_text = " ".join(changed_files[:20])  # Limit to 20 files
        return f"{message} Files: {files_text}"


class VectorIndex:
    """SQLite-based vector index for commit embeddings."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS vector_commits (
        hash TEXT PRIMARY KEY,
        message TEXT NOT NULL,
        changed_files TEXT NOT NULL DEFAULT '[]',
        embedding BLOB NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_vector_commits_hash ON vector_commits(hash);
    """

    def __init__(self, vectors_dir: Path):
        """
        Initialize vector index.

        Args:
            vectors_dir: Path to vectors directory (e.g., .gimi/vectors)
        """
        self.vectors_dir = vectors_dir
        self.db_path = vectors_dir / "vectors.db"
        self._conn: Optional[sqlite3.Connection] = None
        self._dimension: Optional[int] = None

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.vectors_dir.mkdir(parents=True, exist_ok=True)
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

    def add_commit(self, commit: VectorCommit) -> None:
        """
        Add or update a commit with its embedding.

        Args:
            commit: Commit with embedding to add
        """
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO vector_commits
            (hash, message, changed_files, embedding)
            VALUES (?, ?, ?, ?)
            """,
            (commit.hash, commit.message, commit.changed_files, commit.embedding)
        )
        conn.commit()

    def add_commits(self, commits: List[VectorCommit]) -> None:
        """
        Add multiple commits in a batch.

        Args:
            commits: List of commits with embeddings
        """
        conn = self._get_connection()
        conn.execute("BEGIN TRANSACTION")
        try:
            for commit in commits:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO vector_commits
                    (hash, message, changed_files, embedding)
                    VALUES (?, ?, ?, ?)
                    """,
                    (commit.hash, commit.message, commit.changed_files, commit.embedding)
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_commit(self, commit_hash: str) -> Optional[VectorCommit]:
        """
        Get a commit with its embedding by hash.

        Args:
            commit_hash: Commit hash

        Returns:
            VectorCommit or None if not found
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM vector_commits WHERE hash = ?",
            (commit_hash,)
        ).fetchone()

        if row is None:
            return None

        return VectorCommit(
            hash=row["hash"],
            message=row["message"],
            changed_files=row["changed_files"],
            embedding=row["embedding"]
        )

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 20
    ) -> List[Tuple[str, float]]:
        """
        Search for similar commits by embedding.

        This is the main search interface used by the retrieval engine.

        Args:
            query_embedding: Query vector as list of floats
            top_k: Number of results to return

        Returns:
            List of (commit_hash, similarity_score) tuples
        """
        # Convert list of floats to bytes
        embedding_bytes = self._vector_to_bytes(query_embedding)
        return self.search_similar(embedding_bytes, top_k=top_k)

    def search_similar(
        self,
        query_embedding: bytes,
        top_k: int = 20
    ) -> List[Tuple[str, float]]:
        """
        Search for similar commits by embedding.

        Note: This is a basic implementation that loads all vectors and computes
        similarity in Python. For large indexes, consider using a dedicated
        vector database or sqlite-vec extension.

        Args:
            query_embedding: Query vector as bytes (float32 array)
            top_k: Number of results to return

        Returns:
            List of (commit_hash, similarity_score) tuples
        """
        import math

        # Convert query bytes to list of floats
        query_vec = self._bytes_to_vector(query_embedding)

        conn = self._get_connection()
        rows = conn.execute(
            "SELECT hash, embedding FROM vector_commits"
        ).fetchall()

        results = []
        for row in rows:
            commit_hash = row["hash"]
            embedding_bytes = row["embedding"]
            vec = self._bytes_to_vector(embedding_bytes)

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_vec, vec)
            results.append((commit_hash, similarity))

        # Sort by similarity (descending) and take top_k
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    @staticmethod
    def _bytes_to_vector(data: bytes) -> List[float]:
        """Convert bytes to list of floats (float32)."""
        count = len(data) // 4  # 4 bytes per float32
        return list(struct.unpack(f"{count}f", data))

    @staticmethod
    def _vector_to_bytes(vec: List[float]) -> bytes:
        """Convert list of floats to bytes (float32)."""
        return struct.pack(f"{len(vec)}f", *vec)

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b):
            raise ValueError("Vectors must have same dimension")

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        conn = self._get_connection()

        row = conn.execute(
            "SELECT COUNT(*) FROM vector_commits"
        ).fetchone()
        count = row[0] if row else 0

        return {
            "commit_count": count,
            "dimension": self._dimension,
            "db_path": str(self.db_path)
        }
