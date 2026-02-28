"""Retrieval engine that combines keyword, path, and semantic search.

This module provides the RetrievalEngine class that orchestrates
the different retrieval strategies to find relevant commits.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path

from gimi.index.lightweight import LightweightIndex, IndexedCommit
from gimi.index.vector_index import VectorIndex
from gimi.index.embeddings import EmbeddingProvider
from gimi.core.config import RetrievalConfig


@dataclass
class SearchResult:
    """Result from a search query."""
    commit: IndexedCommit
    score: float
    source: str  # 'keyword', 'semantic', 'fusion'


# Alias for backward compatibility
RetrievalResult = SearchResult


class RetrievalEngine:
    """Engine that combines multiple retrieval strategies."""

    def __init__(
        self,
        lightweight_index: LightweightIndex,
        vector_index: VectorIndex,
        embedding_provider: Optional[EmbeddingProvider],
        config: RetrievalConfig
    ):
        """Initialize the retrieval engine.

        Args:
            lightweight_index: The lightweight index for keyword/path search
            vector_index: The vector index for semantic search
            embedding_provider: Provider for generating embeddings
            config: Retrieval configuration
        """
        self.lightweight_index = lightweight_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.config = config

    def search(
        self,
        query: str,
        file_paths: Optional[List[str]] = None,
        branch: Optional[str] = None,
        top_k: Optional[int] = None
    ) -> List[SearchResult]:
        """Search for relevant commits.

        Args:
            query: The search query
            file_paths: Optional list of file paths to filter by
            branch: Optional branch to filter by
            top_k: Number of results to return (overrides config)

        Returns:
            List of search results
        """
        k = top_k or self.config.top_k

        # Phase 1: Get candidates using keyword/path search
        candidates = self._get_candidates(query, file_paths, branch)

        if not candidates:
            return []

        # Phase 2: Rerank using semantic search if available
        results = self._rerank(query, candidates, k)

        return results

    def _get_candidates(
        self,
        query: str,
        file_paths: Optional[List[str]] = None,
        branch: Optional[str] = None
    ) -> List[IndexedCommit]:
        """Get candidate commits using keyword and path search.

        Args:
            query: The search query
            file_paths: Optional file paths to filter by
            branch: Optional branch to filter by

        Returns:
            List of candidate commits
        """
        candidates: Dict[str, IndexedCommit] = {}

        # Search by message content
        message_results = self.lightweight_index.search_by_message(query, limit=self.config.candidate_limit)
        for commit in message_results:
            candidates[commit.hash] = commit

        # Search by file paths
        if file_paths:
            for path in file_paths:
                path_results = self.lightweight_index.search_by_path(path, limit=self.config.candidate_limit)
                for commit in path_results:
                    candidates[commit.hash] = commit

        # Filter by branch if specified
        if branch:
            filtered = {}
            for hash_val, commit in candidates.items():
                if branch in commit.branches:
                    filtered[hash_val] = commit
            candidates = filtered

        return list(candidates.values())

    def _rerank(
        self,
        query: str,
        candidates: List[IndexedCommit],
        top_k: int
    ) -> List[SearchResult]:
        """Rerank candidates using semantic search.

        Args:
            query: The search query
            candidates: List of candidate commits
            top_k: Number of results to return

        Returns:
            List of reranked results
        """
        # If no embedding provider, just return candidates as-is
        if not self.embedding_provider or not self.embedding_provider.is_available():
            results = []
            for commit in candidates[:top_k]:
                results.append(SearchResult(
                    commit=commit,
                    score=1.0,
                    source='keyword'
                ))
            return results

        # Generate query embedding
        query_embedding = self.embedding_provider.embed(query)

        # Score each candidate
        scored_results = []
        for commit in candidates:
            # Get commit embedding from vector index
            commit_embedding = self.vector_index.get_embedding(commit.hash)

            if commit_embedding is not None:
                # Calculate similarity
                similarity = self._cosine_similarity(query_embedding, commit_embedding)
                scored_results.append((commit, similarity))

        # Sort by score and take top_k
        scored_results.sort(key=lambda x: x[1], reverse=True)

        results = []
        for commit, score in scored_results[:top_k]:
            results.append(SearchResult(
                commit=commit,
                score=score,
                source='fusion'
            ))

        return results

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Cosine similarity (between -1 and 1)
        """
        import math

        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = math.sqrt(sum(x * x for x in a))
        magnitude_b = math.sqrt(sum(x * x for x in b))

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)