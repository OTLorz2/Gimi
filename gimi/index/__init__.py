"""Index management for Gimi."""

from gimi.index.lightweight import LightweightIndex, IndexedCommit
from gimi.index.vector_index import VectorIndex, VectorCommit
from gimi.index.embeddings import (
    EmbeddingProvider,
    LocalEmbeddingProvider,
    APIEmbeddingProvider,
    MockEmbeddingProvider,
    get_embedding_provider
)

__all__ = [
    "LightweightIndex",
    "IndexedCommit",
    "VectorIndex",
    "VectorCommit",
    "EmbeddingProvider",
    "LocalEmbeddingProvider",
    "APIEmbeddingProvider",
    "MockEmbeddingProvider",
    "get_embedding_provider",
]
