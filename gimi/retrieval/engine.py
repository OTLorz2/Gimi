"""Retrieval engine for finding relevant commits.

This module implements a hybrid retrieval system that combines:
- Keyword-based retrieval (BM25 on commit messages)
- Path-based retrieval (exact/prefix matching on file paths)
- Semantic retrieval (vector similarity on embeddings)

The results are fused using Reciprocal Rank Fusion (RRF).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from pathlib import Path
import re
import math

import numpy as np

from gimi.index.lightweight import LightweightIndex, CommitMetadata
from gimi.index.vector_index import VectorIndex
from gimi.index.embeddings import EmbeddingProvider


@dataclass
class RetrievalResult:
    """Result from a retrieval operation."""
    commit: CommitMetadata
    score: float = 0.0
    source: str = ""  # e.g., "keyword", "path", "vector", "fusion"
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FusionConfig:
    """Configuration for result fusion."""
    # RRF parameter
    rrf_k: float = 60.0

    # Score weights for each retrieval source
    keyword_weight: float = 1.0
    path_weight: float = 1.0
    vector_weight: float = 1.0

    # Whether to normalize scores before fusion
    normalize_scores: bool = True

    # Boost factor for commits that match multiple sources
    multi_match_boost: float = 1.1


def reciprocal_rank_fusion(
    rankings: Dict[str, List[RetrievalResult]],
    config: FusionConfig
) -> List[RetrievalResult]:
    """Fuse multiple rankings using Reciprocal Rank Fusion (RRF).

    RRF formula: score = sum(weight / (k + rank))

    Args:
        rankings: Dict mapping source name to ranked list of results
        config: Fusion configuration

    Returns:
        Fused and re-ranked list of results
    """
    # Collect all commit hashes and their ranks in each source
    commit_scores: Dict[str, Dict[str, Any]] = {}

    for source_name, results in rankings.items():
        # Get weight for this source
        if source_name == "keyword":
            weight = config.keyword_weight
        elif source_name == "path":
            weight = config.path_weight
        elif source_name == "vector":
            weight = config.vector_weight
        else:
            weight = 1.0

        for rank, result in enumerate(results, start=1):
            commit_hash = result.commit.hash

            if commit_hash not in commit_scores:
                commit_scores[commit_hash] = {
                    'commit': result.commit,
                    'rrf_score': 0.0,
                    'sources': set(),
                    'details': {}
                }

            # RRF formula: weight / (k + rank)
            rrf_score = weight / (config.rrf_k + rank)
            commit_scores[commit_hash]['rrf_score'] += rrf_score
            commit_scores[commit_hash]['sources'].add(source_name)
            commit_scores[commit_hash]['details'][source_name] = {
                'rank': rank,
                'original_score': result.score
            }

    # Apply multi-match boost
    for commit_hash, data in commit_scores.items():
        if len(data['sources']) > 1:
            data['rrf_score'] *= config.multi_match_boost

    # Sort by RRF score
    sorted_commits = sorted(
        commit_scores.items(),
        key=lambda x: x[1]['rrf_score'],
        reverse=True
    )

    # Create results
    results = []
    for commit_hash, data in sorted_commits:
        result = RetrievalResult(
            commit=data['commit'],
            score=data['rrf_score'],
            source='fusion',
            details={
                'sources': list(data['sources']),
                'source_details': data['details']
            }
        )
        results.append(result)

    return results


class BM25Index:
    """Simple BM25 implementation for keyword retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """Initialize BM25 index.

        Args:
            k1: BM25 k1 parameter
            b: BM25 b parameter
        """
        self.k1 = k1
        self.b = b
        self.documents: List[str] = []
        self.doc_tokens: List[List[str]] = []
        self.doc_freqs: Dict[str, int] = {}
        self.total_tokens = 0
        self.avg_doc_len = 0.0

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens
        """
        # Simple word tokenization with lowercase
        return re.findall(r'\b[a-zA-Z]+\b', text.lower())

    def add_document(self, doc_id: int, text: str) -> None:
        """Add document to index.

        Args:
            doc_id: Document ID
            text: Document text
        """
        tokens = self._tokenize(text)

        # Extend lists if needed
        while len(self.documents) <= doc_id:
            self.documents.append("")
            self.doc_tokens.append([])

        self.documents[doc_id] = text
        self.doc_tokens[doc_id] = tokens

        # Update document frequencies
        unique_tokens = set(tokens)
        for token in unique_tokens:
            self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1

        # Update statistics
        self.total_tokens += len(tokens)
        self.avg_doc_len = self.total_tokens / len([t for t in self.doc_tokens if t])

    def search(self, query: str, top_k: int = 10) -> List[tuple]:
        """Search documents with BM25 scoring.

        Args:
            query: Search query
            top_k: Number of top results to return

        Returns:
            List of (doc_id, score) tuples
        """
        query_tokens = self._tokenize(query)

        if not query_tokens:
            return []

        scores = []
        num_docs = len(self.documents)

        for doc_id, doc_tokens in enumerate(self.doc_tokens):
            if not doc_tokens:
                continue

            score = 0.0
            doc_len = len(doc_tokens)

            for token in query_tokens:
                # Document frequency
                df = self.doc_freqs.get(token, 0)
                if df == 0:
                    continue

                # IDF calculation
                idf = math.log((num_docs - df + 0.5) / (df + 0.5) + 1)

                # Term frequency in document
                tf = doc_tokens.count(token)

                # BM25 scoring
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len)
                if denom > 0:
                    score += idf * tf * (self.k1 + 1) / denom

            if score > 0:
                scores.append((doc_id, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:top_k]


class RetrievalEngine:
    """Hybrid retrieval engine combining multiple retrieval strategies."""

    def __init__(
        self,
        lightweight_index: LightweightIndex,
        vector_index: VectorIndex,
        embedding_provider: EmbeddingProvider,
        config: Any
    ):
        """Initialize retrieval engine.

        Args:
            lightweight_index: Lightweight index for keyword/path retrieval
            vector_index: Vector index for semantic retrieval
            embedding_provider: Provider for generating embeddings
            config: Retrieval configuration
        """
        self.lightweight_index = lightweight_index
        self.vector_index = vector_index
        self.embedding_provider = embedding_provider
        self.config = config

        # Initialize fusion config
        self.fusion_config = FusionConfig(
            rrf_k=getattr(config, 'rrf_k', 60.0),
            keyword_weight=getattr(config, 'keyword_weight', 1.0),
            path_weight=getattr(config, 'path_weight', 1.0),
            vector_weight=getattr(config, 'vector_weight', 1.0),
            normalize_scores=getattr(config, 'normalize_scores', True),
            multi_match_boost=getattr(config, 'multi_match_boost', 1.1)
        )

        # Build BM25 index from lightweight index
        self._bm25_index: Optional[BM25Index] = None

    def _build_bm25_index(self) -> BM25Index:
        """Build BM25 index from lightweight index.

        Returns:
            BM25Index instance
        """
        if self._bm25_index is not None:
            return self._bm25_index

        bm25 = BM25Index()

        # Get all commits from lightweight index
        if hasattr(self.lightweight_index, 'commits'):
            commits = self.lightweight_index.commits
            for idx, commit in enumerate(commits):
                # Index commit message
                text = f"{commit.message}\n{' '.join(commit.files)}"
                bm25.add_document(idx, text)

        self._bm25_index = bm25
        return bm25

    def _keyword_search(
        self,
        query: str,
        top_k: int = 50
    ) -> List[RetrievalResult]:
        """Search using keyword matching (BM25).

        Args:
            query: Search query
            top_k: Number of top results

        Returns:
            List of retrieval results
        """
        bm25 = self._build_bm25_index()
        results = bm25.search(query, top_k=top_k)

        retrieval_results = []
        if hasattr(self.lightweight_index, 'commits'):
            commits = self.lightweight_index.commits
            for doc_id, score in results:
                if 0 <= doc_id < len(commits):
                    retrieval_results.append(RetrievalResult(
                        commit=commits[doc_id],
                        score=score,
                        source="keyword"
                    ))

        return retrieval_results

    def _path_search(
        self,
        file_paths: List[str],
        top_k: int = 50
    ) -> List[RetrievalResult]:
        """Search using file path matching.

        Args:
            file_paths: List of file paths to match
            top_k: Number of top results

        Returns:
            List of retrieval results
        """
        if not hasattr(self.lightweight_index, 'commits'):
            return []

        commits = self.lightweight_index.commits
        scores: Dict[str, float] = {}

        for commit in commits:
            score = 0.0
            for file_path in file_paths:
                # Check if file path matches any changed file
                for changed_file in commit.files:
                    if file_path in changed_file or changed_file in file_path:
                        score += 1.0
                    elif Path(file_path).name in changed_file:
                        score += 0.5

            if score > 0:
                scores[commit.hash] = score

        # Sort by score and create results
        sorted_commits = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]

        commit_map = {c.hash: c for c in commits}
        results = []
        for commit_hash, score in sorted_commits:
            if commit_hash in commit_map:
                results.append(RetrievalResult(
                    commit=commit_map[commit_hash],
                    score=score,
                    source="path"
                ))

        return results

    def _vector_search(
        self,
        query: str,
        top_k: int = 50
    ) -> List[RetrievalResult]:
        """Search using vector similarity.

        Args:
            query: Search query
            top_k: Number of top results

        Returns:
            List of retrieval results
        """
        # Generate query embedding
        query_embedding = self.embedding_provider.embed_single(query)

        # Search vector index
        results = self.vector_index.search(
            query_embedding=query_embedding,
            top_k=top_k
        )

        # Convert to RetrievalResult
        retrieval_results = []
        for commit_hash, score in results:
            # Get commit metadata from lightweight index
            commit = self.lightweight_index.get_commit(commit_hash)
            if commit:
                retrieval_results.append(RetrievalResult(
                    commit=commit,
                    score=float(score),
                    source="vector"
                ))

        return retrieval_results

    def search(
        self,
        query: str,
        file_paths: Optional[List[str]] = None,
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """Search for relevant commits using hybrid retrieval.

        Args:
            query: Search query
            file_paths: Optional file paths to filter by
            top_k: Number of top results (defaults to config.top_k)

        Returns:
            List of retrieval results ranked by relevance
        """
        if top_k is None:
            top_k = getattr(self.config, 'top_k', 10)

        # Phase 1: Retrieve from multiple sources
        rankings: Dict[str, List[RetrievalResult]] = {}

        # Keyword search
        keyword_results = self._keyword_search(query, top_k=top_k * 3)
        if keyword_results:
            rankings["keyword"] = keyword_results

        # Path search (if file paths provided)
        if file_paths:
            path_results = self._path_search(file_paths, top_k=top_k * 3)
            if path_results:
                rankings["path"] = path_results

        # Vector search
        vector_results = self._vector_search(query, top_k=top_k * 3)
        if vector_results:
            rankings["vector"] = vector_results

        # If no results from any source, return empty list
        if not rankings:
            return []

        # Phase 2: Fuse rankings using RRF
        fused_results = reciprocal_rank_fusion(rankings, self.fusion_config)

        # Return top_k results
        return fused_results[:top_k]

    def search_with_reranking(
        self,
        query: str,
        file_paths: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        rerank_k: int = 20
    ) -> List[RetrievalResult]:
        """Search with optional second-stage reranking.

        This method retrieves a larger candidate set and then
        reranks them using a more expensive scoring function.

        Args:
            query: Search query
            file_paths: Optional file paths to filter by
            top_k: Number of top results to return
            rerank_k: Number of candidates to rerank

        Returns:
            List of retrieval results
        """
        # Get larger candidate set
        candidates = self.search(query, file_paths, top_k=rerank_k)

        if not candidates:
            return []

        # Rerank using cross-encoder style scoring
        reranked = self._rerank_candidates(query, candidates)

        return reranked[:top_k]

    def _rerank_candidates(
        self,
        query: str,
        candidates: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """Rerank candidates using query-specific scoring.

        This implements a lightweight reranking that considers
        the specific query terms and their match quality.

        Args:
            query: Original search query
            candidates: Candidate results to rerank

        Returns:
            Reranked list of results
        """
        query_terms = set(re.findall(r'\b[a-zA-Z]+\b', query.lower()))

        reranked = []
        for result in candidates:
            score = result.score

            # Boost based on term overlap with commit message
            message_terms = set(re.findall(
                r'\b[a-zA-Z]+\b',
                result.commit.message.lower()
            ))

            if query_terms:
                overlap = len(query_terms & message_terms)
                overlap_ratio = overlap / len(query_terms)
                score *= (1 + overlap_ratio)

            # Boost for recent commits
            if hasattr(result.commit, 'timestamp'):
                # Normalize timestamp to 0-1 range (approximate)
                # More recent = higher score
                import time
                age_days = (time.time() - result.commit.timestamp) / 86400
                recency_boost = 1.0 / (1 + age_days / 30)  # Decay over ~month
                score *= (1 + recency_boost * 0.1)

            reranked.append(RetrievalResult(
                commit=result.commit,
                score=score,
                source=result.source,
                details={**result.details, 'reranked': True}
            ))

        # Sort by new score
        reranked.sort(key=lambda x: x.score, reverse=True)
        return reranked


class RetrievalConfig:
    """Configuration for retrieval engine."""

    def __init__(
        self,
        top_k: int = 10,
        rrf_k: float = 60.0,
        keyword_weight: float = 1.0,
        path_weight: float = 1.0,
        vector_weight: float = 1.0,
        normalize_scores: bool = True,
        multi_match_boost: float = 1.1,
        enable_reranking: bool = False,
        rerank_k: int = 20
    ):
        """Initialize retrieval config.

        Args:
            top_k: Number of top results to return
            rrf_k: RRF fusion parameter
            keyword_weight: Weight for keyword scores
            path_weight: Weight for path scores
            vector_weight: Weight for vector scores
            normalize_scores: Whether to normalize scores
            multi_match_boost: Boost for multi-source matches
            enable_reranking: Whether to enable reranking
            rerank_k: Number of candidates to rerank
        """
        self.top_k = top_k
        self.rrf_k = rrf_k
        self.keyword_weight = keyword_weight
        self.path_weight = path_weight
        self.vector_weight = vector_weight
        self.normalize_scores = normalize_scores
        self.multi_match_boost = multi_match_boost
        self.enable_reranking = enable_reranking
        self.rerank_k = rerank_k
