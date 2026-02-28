"""Retrieval engine for hybrid search (keyword + path + semantic)."""

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
import json

from gimi.core.config import RetrievalConfig
from gimi.index.lightweight import LightweightIndex, IndexedCommit
from gimi.index.vector_index import VectorIndex
from gimi.index.embeddings import EmbeddingProvider


class RetrievalError(Exception):
    """Raised when retrieval fails."""
    pass


@dataclass
class RetrievalResult:
    """Result of a retrieval operation."""
    commit: IndexedCommit
    keyword_score: float = 0.0
    path_score: float = 0.0
    semantic_score: float = 0.0
    combined_score: float = 0.0


@dataclass
class RetrievalStats:
    """Statistics for retrieval operation."""
    candidate_count: int = 0
    keyword_filtered_count: int = 0
    path_filtered_count: int = 0
    semantic_search_count: int = 0
    final_count: int = 0
    total_time_ms: float = 0.0


class RetrievalEngine:
    """Hybrid retrieval engine combining keyword, path, and semantic search."""

    def __init__(
        self,
        lightweight_index: LightweightIndex,
        vector_index: VectorIndex,
        embedding_provider: EmbeddingProvider,
        config: RetrievalConfig
    ):
        """
        Initialize retrieval engine.

        Args:
            lightweight_index: SQLite-based lightweight index
            vector_index: Vector index for semantic search
            embedding_provider: Provider for generating embeddings
            config: Retrieval configuration
        """
        self.lightweight_index = lightweight_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.config = config
        self._stats: Optional[RetrievalStats] = None

    def search(
        self,
        query: str,
        file_paths: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> List[RetrievalResult]:
        """
        Perform hybrid search combining keyword, path, and semantic retrieval.

        Args:
            query: User query text
            file_paths: Optional list of file paths to filter by
            progress_callback: Optional callback for progress updates

        Returns:
            List of retrieval results sorted by combined score
        """
        import time
        start_time = time.time()

        self._stats = RetrievalStats()

        # Stage 1: Keyword and path retrieval (T10)
        candidates = self._get_candidates(query, file_paths)
        self._stats.candidate_count = len(candidates)

        if progress_callback:
            progress_callback("Keyword/Path retrieval", len(candidates), len(candidates))

        if not candidates:
            self._stats.total_time_ms = (time.time() - start_time) * 1000
            return []

        # Stage 2: Semantic retrieval and fusion (T11)
        results = self._semantic_fusion(query, candidates)
        self._stats.semantic_search_count = len(results)

        if progress_callback:
            progress_callback("Semantic fusion", len(results), len(results))

        # Stage 3: Optional two-stage reranking (T12)
        if self.config.enable_rerank:
            results = self._rerank(query, results)

            if progress_callback:
                progress_callback("Reranking", len(results), len(results))

        self._stats.final_count = len(results)
        self._stats.total_time_ms = (time.time() - start_time) * 1000

        return results

    def _get_candidates(
        self,
        query: str,
        file_paths: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        Get candidate commits using keyword and path search.

        Args:
            query: Search query
            file_paths: Optional file paths to filter by

        Returns:
            Dictionary mapping commit hash to keyword/path score
        """
        candidates: Dict[str, float] = {}

        # Keyword search on message and author
        keyword_results = self.lightweight_index.search_by_message(
            query, limit=self.config.keyword_candidates
        )

        for commit in keyword_results:
            # Simple score based on position
            score = 1.0 / (keyword_results.index(commit) + 1)
            candidates[commit.hash] = score

        # Path-based filtering
        if file_paths:
            for path_pattern in file_paths:
                path_results = self.lightweight_index.search_by_path(
                    path_pattern, limit=self.config.keyword_candidates
                )

                for commit in path_results:
                    score = 1.0 / (path_results.index(commit) + 1)
                    if commit.hash in candidates:
                        candidates[commit.hash] = max(candidates[commit.hash], score)
                    else:
                        candidates[commit.hash] = score

        return candidates

    def _semantic_fusion(
        self,
        query: str,
        candidates: Dict[str, float]
    ) -> List[RetrievalResult]:
        """
        Perform semantic search on candidates and fuse scores.

        Args:
            query: User query
            candidates: Candidate commits with keyword/path scores

        Returns:
            List of retrieval results sorted by combined score
        """
        # Generate query embedding
        query_embedding = self.embedding_provider.embed_single(query)

        # Convert to bytes for vector search
        query_bytes = struct.pack(f"{len(query_embedding)}f", *query_embedding)

        # Search in vector index
        vector_results = self.vector_index.search_similar(
            query_bytes, top_k=len(candidates)
        )

        # Map hash to similarity score
        semantic_scores = {h: s for h, s in vector_results}

        # Create retrieval results with fused scores
        results = []
        for commit_hash, keyword_score in candidates.items():
            commit = self.lightweight_index.get_commit(commit_hash)
            if commit is None:
                continue

            semantic_score = semantic_scores.get(commit_hash, 0.0)

            # Simple weighted fusion - could use RRF for better results
            combined_score = 0.3 * keyword_score + 0.7 * semantic_score

            results.append(RetrievalResult(
                commit=commit,
                keyword_score=keyword_score,
                semantic_score=semantic_score,
                combined_score=combined_score
            ))

        # Sort by combined score descending
        results.sort(key=lambda x: x.combined_score, reverse=True)

        return results[:self.config.top_k]

    def _rerank(
        self,
        query: str,
        results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """
        Optional two-stage reranking using cross-encoder or LLM.

        Args:
            query: User query
            results: Initial retrieval results

        Returns:
            Reranked results
        """
        # For now, this is a placeholder
        # A full implementation would use a cross-encoder model
        # or an LLM to score relevance

        # Take top results from initial ranking
        return results[:self.config.rerank_top_k]

    def get_stats(self) -> Optional[RetrievalStats]:
        """Get statistics from the last search operation."""
        return self._stats
