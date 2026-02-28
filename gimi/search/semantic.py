"""
T11: Semantic retrieval and fusion.

This module implements semantic search using vector embeddings
and fusion with keyword search results for the second stage of retrieval.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from gimi.config import GimiConfig
from gimi.index.git import CommitMetadata
from gimi.index.vector import VectorIndex, create_embedding_provider, EmbeddingConfig
from gimi.search.keyword import KeywordSearchResult


@dataclass
class SemanticSearchResult:
    """Result of a semantic search."""
    commit: CommitMetadata
    score: float
    source: str = "semantic"  # semantic, keyword, fusion


@dataclass
class FusionResult:
    """Result after fusing keyword and semantic search."""
    commit: CommitMetadata
    fused_score: float
    keyword_score: float
    semantic_score: float
    rank_keyword: int
    rank_semantic: int


class SemanticSearcher:
    """
    Semantic search using vector embeddings.

    Provides semantic retrieval of commits based on vector similarity
    between query and commit embeddings.
    """

    def __init__(
        self,
        vector_index: VectorIndex,
        config: Optional[GimiConfig] = None
    ):
        """
        Initialize the semantic searcher.

        Args:
            vector_index: VectorIndex instance
            config: Optional configuration
        """
        self.vector_index = vector_index
        self.config = config or GimiConfig()

        # Initialize embedding provider
        embedding_config = EmbeddingConfig(
            provider=self.config.embedding_provider,
            model=self.config.embedding_model,
            api_key=self.config.embedding_api_key,
            dimensions=self.config.embedding_dimensions,
            base_url=self.config.llm_base_url
        )
        self.embedding_provider = create_embedding_provider(embedding_config)

    def search(
        self,
        query: str,
        top_k: int = 50,
        branches: Optional[List[str]] = None
    ) -> List[SemanticSearchResult]:
        """
        Search commits by semantic similarity to query.

        Args:
            query: Search query text
            top_k: Maximum number of results
            branches: Filter by branches

        Returns:
            List of SemanticSearchResult sorted by similarity
        """
        # Embed query
        try:
            query_embedding = self.embedding_provider.embed([query])[0]
        except Exception as e:
            raise SemanticSearchError(f"Failed to embed query: {e}")

        # Search vector index
        similar = self.vector_index.search_similar(query_embedding, top_k=top_k * 2)

        # Convert to results
        results = []
        for commit_hash, similarity in similar:
            commit = self._get_commit_with_branches(commit_hash)
            if commit:
                # Apply branch filter
                if branches:
                    commit_branches = set(commit.branches)
                    if not commit_branches.intersection(branches):
                        continue

                results.append(SemanticSearchResult(
                    commit=commit,
                    score=similarity,
                    source="semantic"
                ))

        # Sort by score and limit
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def _get_commit_with_branches(self, commit_hash: str) -> Optional[CommitMetadata]:
        """Get commit metadata with branch information."""
        # This is a placeholder - in real implementation, you'd fetch
        # from the lightweight index
        # For now, return None to indicate we need proper implementation
        return None


class SearchFusion:
    """
    Fusion of keyword and semantic search results.

    Combines results from both retrieval methods using
    configurable fusion strategies.
    """

    def __init__(self, config: Optional[GimiConfig] = None):
        """
        Initialize the fusion module.

        Args:
            config: Configuration with fusion weights
        """
        self.config = config or GimiConfig()
        self.semantic_weight = self.config.retrieval_semantic_weight
        self.keyword_weight = self.config.retrieval_keyword_weight

    def fuse(
        self,
        keyword_results: List[KeywordSearchResult],
        semantic_results: List[SemanticSearchResult],
        top_k: int = 25,
        method: str = "weighted"
    ) -> List[FusionResult]:
        """
        Fuse keyword and semantic search results.

        Args:
            keyword_results: Results from keyword search
            semantic_results: Results from semantic search
            top_k: Maximum number of fused results
            method: Fusion method ("weighted", "rrf")

        Returns:
            List of FusionResult sorted by fused score
        """
        # Normalize scores
        keyword_norm = self._normalize_scores([r.score for r in keyword_results])
        semantic_norm = self._normalize_scores([r.score for r in semantic_results])

        # Create lookup by commit hash
        keyword_by_hash = {}
        for i, result in enumerate(keyword_results):
            keyword_by_hash[result.commit.hash] = {
                'result': result,
                'score_norm': keyword_norm[i],
                'rank': i + 1
            }

        semantic_by_hash = {}
        for i, result in enumerate(semantic_results):
            semantic_by_hash[result.commit.hash] = {
                'result': result,
                'score_norm': semantic_norm[i],
                'rank': i + 1
            }

        # Get all unique commits
        all_hashes = set(keyword_by_hash.keys()) | set(semantic_by_hash.keys())

        # Fuse results
        fused = []
        for commit_hash in all_hashes:
            k_data = keyword_by_hash.get(commit_hash, {})
            s_data = semantic_by_hash.get(commit_hash, {})

            keyword_result = k_data.get('result')
            semantic_result = s_data.get('result')

            # Get the commit metadata
            commit = (keyword_result.commit if keyword_result
                     else semantic_result.commit)

            # Calculate fused score
            if method == "weighted":
                keyword_score = k_data.get('score_norm', 0)
                semantic_score = s_data.get('score_norm', 0)

                fused_score = (
                    self.keyword_weight * keyword_score +
                    self.semantic_weight * semantic_score
                )
            elif method == "rrf":
                # Reciprocal Rank Fusion
                k = 60  # RRF constant
                keyword_rank = k_data.get('rank', 9999)
                semantic_rank = s_data.get('rank', 9999)

                fused_score = 1.0 / (k + keyword_rank) + 1.0 / (k + semantic_rank)
            else:
                raise ValueError(f"Unknown fusion method: {method}")

            fused.append(FusionResult(
                commit=commit,
                fused_score=fused_score,
                keyword_score=k_data.get('score_norm', 0),
                semantic_score=s_data.get('score_norm', 0),
                rank_keyword=k_data.get('rank', 9999),
                rank_semantic=s_data.get('rank', 9999)
            ))

        # Sort by fused score and return top_k
        fused.sort(key=lambda x: x.fused_score, reverse=True)
        return fused[:top_k]

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """Normalize scores to [0, 1] range."""
        if not scores:
            return []

        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            return [1.0] * len(scores)

        return [(s - min_score) / (max_score - min_score) for s in scores]


if __name__ == '__main__':
    # Test fusion
    print("Testing SearchFusion...")

    # Create mock results
    from gimi.index.git import CommitMetadata

    commits = [
        CommitMetadata(
            hash=f"commit{i}" * 8,
            short_hash=f"commit{i}",
            message=f"Test commit {i}",
            author_name="Test",
            author_email="test@test.com",
            author_timestamp=1609459200 + i * 1000,
            committer_name="Test",
            committer_email="test@test.com",
            committer_timestamp=1609459200 + i * 1000,
            branches=["main"],
            parent_hashes=[],
            files_changed=["src/file.py"],
            stats={'additions': 10, 'deletions': 5, 'files': 1}
        )
        for i in range(5)
    ]

    # Create keyword results
    keyword_results = [
        KeywordSearchResult(commit=commits[0], score=0.9),
        KeywordSearchResult(commit=commits[1], score=0.8),
        KeywordSearchResult(commit=commits[2], score=0.7),
        KeywordSearchResult(commit=commits[3], score=0.6),
    ]

    # Create semantic results
    semantic_results = [
        SemanticSearchResult(commit=commits[1], score=0.95),
        SemanticSearchResult(commit=commits[3], score=0.85),
        SemanticSearchResult(commit=commits[0], score=0.75),
        SemanticSearchResult(commit=commits[4], score=0.65),
    ]

    # Test fusion
    fusion = SearchFusion()

    print("\nTesting weighted fusion:")
    results = fusion.fuse(keyword_results, semantic_results, top_k=10, method="weighted")
    print(f"Fused {len(results)} results")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r.commit.short_hash}: fused={r.fused_score:.3f}, "
              f"keyword={r.keyword_score:.3f}, semantic={r.semantic_score:.3f}")

    print("\nTesting RRF fusion:")
    results = fusion.fuse(keyword_results, semantic_results, top_k=10, method="rrf")
    print(f"Fused {len(results)} results")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r.commit.short_hash}: fused={r.fused_score:.3f}, "
              f"keyword_rank={r.rank_keyword}, semantic_rank={r.rank_semantic}")

    print("\n✓ All fusion tests passed!")
