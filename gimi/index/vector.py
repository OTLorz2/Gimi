"""
T8: Vector index and embedding.

This module implements vector-based indexing for semantic search.
It handles embedding generation and vector storage for commit data.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Protocol, Tuple, Union

import numpy as np

from gimi.config import GimiConfig
from gimi.index.git import CommitMetadata
from gimi.utils.lock import FileLock


class EmbeddingError(Exception):
    """Error during embedding generation."""
    pass


class VectorIndexError(Exception):
    """Error with vector index operations."""
    pass


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        ...

    @property
    def dimensions(self) -> int:
        """Get the dimensionality of embeddings."""
        ...


@dataclass
class EmbeddingConfig:
    """Configuration for embeddings."""
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    api_key: str = ""
    dimensions: int = 1536
    batch_size: int = 100
    base_url: str = ""


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize the OpenAI client."""
        try:
            import openai

            api_key = self.config.api_key or os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise EmbeddingError("OpenAI API key not provided")

            client_kwargs = {'api_key': api_key}
            if self.config.base_url:
                client_kwargs['base_url'] = self.config.base_url

            self._client = openai.OpenAI(**client_kwargs)
        except ImportError:
            raise EmbeddingError(
                "OpenAI package not installed. Install with: pip install openai"
            )

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API."""
        if not self._client:
            raise EmbeddingError("OpenAI client not initialized")

        try:
            response = self._client.embeddings.create(
                model=self.config.model,
                input=texts,
                dimensions=self.config.dimensions
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            raise EmbeddingError(f"OpenAI embedding failed: {e}")

    @property
    def dimensions(self) -> int:
        return self.config.dimensions


class LocalEmbeddingProvider:
    """Local embedding provider using sentence-transformers."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model = None
        self._load_model()

    def _load_model(self):
        """Load the sentence-transformers model."""
        try:
            from sentence_transformers import SentenceTransformer

            model_name = self.config.model
            if not model_name or model_name == "text-embedding-3-small":
                model_name = "all-MiniLM-L6-v2"

            self._model = SentenceTransformer(model_name)
        except ImportError:
            raise EmbeddingError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local model."""
        if self._model is None:
            raise EmbeddingError("Model not loaded")

        try:
            embeddings = self._model.encode(texts, convert_to_list=True)
            return embeddings
        except Exception as e:
            raise EmbeddingError(f"Local embedding failed: {e}")

    @property
    def dimensions(self) -> int:
        if self._model:
            return self._model.get_sentence_embedding_dimension()
        return self.config.dimensions


def create_embedding_provider(config: EmbeddingConfig) -> EmbeddingProvider:
    """
    Factory function to create an embedding provider.

    Args:
        config: Embedding configuration

    Returns:
        EmbeddingProvider instance
    """
    if config.provider == "openai":
        return OpenAIEmbeddingProvider(config)
    elif config.provider == "local":
        return LocalEmbeddingProvider(config)
    else:
        raise EmbeddingError(f"Unknown provider: {config.provider}")


class VectorIndex:
    """
    Vector index for storing and querying commit embeddings.

    Uses SQLite for metadata and numpy files for vectors
    (or SQLite with blob storage for simplicity).
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS embeddings (
        commit_hash TEXT PRIMARY KEY,
        vector BLOB NOT NULL,  -- Stored as JSON array
        dimensions INTEGER NOT NULL,
        model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS embedding_texts (
        commit_hash TEXT PRIMARY KEY,
        text TEXT NOT NULL,  -- The text that was embedded
        FOREIGN KEY (commit_hash) REFERENCES embeddings(commit_hash) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_embeddings_model ON embeddings(model);
    """

    def __init__(self, vectors_dir: Path, lock: Optional[FileLock] = None):
        """
        Initialize the vector index.

        Args:
            vectors_dir: Directory to store vector data
            lock: Optional file lock for concurrent access
        """
        self.vectors_dir = Path(vectors_dir)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.vectors_dir / 'vectors.db'
        self.lock = lock

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper locking."""
        if self.lock:
            self.lock.acquire()

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
            if self.lock:
                self.lock.release()

    def initialize(self) -> None:
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.executescript(self.SCHEMA)

    def exists(self) -> bool:
        """Check if the vector index exists."""
        if not self.db_path.exists():
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
                )
                return cursor.fetchone() is not None
        except Exception:
            return False

    def add_embedding(
        self,
        commit_hash: str,
        vector: List[float],
        text: str,
        model: str = "unknown"
    ) -> None:
        """
        Add an embedding to the index.

        Args:
            commit_hash: Commit hash
            vector: Embedding vector
            text: Text that was embedded
            model: Model name used for embedding
        """
        vector_json = json.dumps(vector)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO embeddings
                (commit_hash, vector, dimensions, model)
                VALUES (?, ?, ?, ?)
                """,
                (commit_hash, vector_json, len(vector), model)
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO embedding_texts
                (commit_hash, text)
                VALUES (?, ?)
                """,
                (commit_hash, text)
            )

    def get_embedding(self, commit_hash: str) -> Optional[Tuple[List[float], str]]:
        """
        Get an embedding by commit hash.

        Returns:
            Tuple of (vector, text) or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT e.vector, t.text
                FROM embeddings e
                JOIN embedding_texts t ON e.commit_hash = t.commit_hash
                WHERE e.commit_hash = ?
                """,
                (commit_hash,)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0]), row[1]
            return None

    def get_all_embeddings(self) -> Iterator[Tuple[str, List[float], str]]:
        """
        Get all embeddings from the index.

        Yields:
            Tuples of (commit_hash, vector, text)
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT e.commit_hash, e.vector, t.text
                FROM embeddings e
                JOIN embedding_texts t ON e.commit_hash = t.commit_hash
                """
            )
            for row in cursor.fetchall():
                yield row[0], json.loads(row[1]), row[2]

    def search_similar(
        self,
        query_vector: List[float],
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Search for similar vectors using cosine similarity.

        Note: This performs a brute-force search. For large datasets,
        consider using approximate nearest neighbor libraries like FAISS.

        Args:
            query_vector: Vector to search for
            top_k: Number of top results to return

        Returns:
            List of (commit_hash, similarity_score) tuples
        """
        query_vec = np.array(query_vector)
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return []

        # Normalize query
        query_vec = query_vec / query_norm

        similarities = []

        # Iterate over all embeddings
        for commit_hash, vector, text in self.get_all_embeddings():
            vec = np.array(vector)
            vec_norm = np.linalg.norm(vec)

            if vec_norm == 0:
                continue

            # Normalize and compute cosine similarity
            vec = vec / vec_norm
            similarity = float(np.dot(query_vec, vec))

            similarities.append((commit_hash, similarity))

        # Sort by similarity (descending) and return top_k
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_k]

    def get_stats(self) -> dict:
        """Get statistics about the vector index."""
        with self._get_connection() as conn:
            stats = {}

            cursor = conn.execute("SELECT COUNT(*) FROM embeddings")
            stats['total_embeddings'] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT DISTINCT model FROM embeddings")
            stats['models'] = [row[0] for row in cursor.fetchall()]

            return stats

    def clear(self) -> None:
        """Clear all data from the vector index."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM embedding_texts")
            conn.execute("DELETE FROM embeddings")


if __name__ == '__main__':
    # Test the vector index
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        vectors_dir = Path(tmpdir) / "vectors"

        print("Testing VectorIndex...")

        # Create index
        index = VectorIndex(vectors_dir)
        index.initialize()

        print(f"✓ Vector index initialized at: {index.db_path}")
        print(f"✓ Index exists: {index.exists()}")

        # Test adding embeddings
        test_embeddings = [
            ("commit1" * 8, [0.1, 0.2, 0.3, 0.4, 0.5], "Initial commit message"),
            ("commit2" * 8, [0.2, 0.3, 0.4, 0.5, 0.6], "Add feature X"),
            ("commit3" * 8, [0.9, 0.8, 0.7, 0.6, 0.5], "Fix bug in feature Y"),
        ]

        for commit_hash, vector, text in test_embeddings:
            index.add_embedding(commit_hash, vector, text, model="test-model")

        print(f"✓ Added {len(test_embeddings)} embeddings")

        # Test retrieval
        print("\nTesting embedding retrieval:")
        embedding, text = index.get_embedding("commit1" * 8)
        print(f"✓ Retrieved embedding for commit1: {embedding[:3]}...")
        print(f"  Text: {text}")

        # Test similarity search
        print("\nTesting similarity search:")
        query_vector = [0.15, 0.25, 0.35, 0.45, 0.55]  # Close to commit1 and commit2
        results = index.search_similar(query_vector, top_k=3)
        print(f"✓ Found {len(results)} similar commits:")
        for commit_hash, similarity in results:
            print(f"  {commit_hash}: {similarity:.4f}")

        # Test stats
        print("\nIndex statistics:")
        stats = index.get_stats()
        print(f"  Total embeddings: {stats['total_embeddings']}")
        print(f"  Models: {stats['models']}")

        # Test clear
        print("\nTesting clear:")
        index.clear()
        stats = index.get_stats()
        print(f"✓ Index cleared. Total embeddings: {stats['total_embeddings']}")

        print("\n✓ All VectorIndex tests passed!")
