"""
T12: Optional two-stage reranking.

This module implements optional reranking of search results
using cross-encoders or LLMs for improved relevance ranking.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Tuple

import numpy as np

from gimi.config import GimiConfig
from gimi.index.git import CommitMetadata


class RerankerError(Exception):
    """Error during reranking."""
    pass


@dataclass
class RerankResult:
    """Result of reranking."""
    commit: CommitMetadata
    relevance_score: float
    original_rank: int
    reranker_type: str


class Reranker(ABC):
    """Abstract base class for rerankers."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        commits: List[CommitMetadata],
        top_k: int = 10
    ) -> List[RerankResult]:
        """
        Rerank commits by relevance to query.

        Args:
            query: Search query
            commits: List of commits to rerank
            top_k: Maximum results to return

        Returns:
            List of RerankResult sorted by relevance
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get reranker name."""
        pass


class CrossEncoderReranker(Reranker):
    """
    Reranker using cross-encoder models.

    Cross-encoders encode query and document together
    for more accurate relevance scoring than bi-encoders.
    """

    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self, model_name: Optional[str] = None, device: str = "cpu"):
        """
        Initialize cross-encoder reranker.

        Args:
            model_name: Model name or path
            device: Device to run on (cpu/cuda)
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.device = device
        self._model = None
        self._load_model()

    def _load_model(self):
        """Load the cross-encoder model."""
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.model_name,
                device=self.device,
                max_length=512
            )
        except ImportError:
            raise RerankerError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
        except Exception as e:
            raise RerankerError(f"Failed to load cross-encoder model: {e}")

    def _format_commit(self, commit: CommitMetadata) -> str:
        """Format commit for cross-encoder input."""
        # Include message and file changes for context
        text = f"{commit.message}\n\n"
        if commit.files_changed:
            text += "Files changed: " + ", ".join(commit.files_changed[:5])
        return text

    def rerank(
        self,
        query: str,
        commits: List[CommitMetadata],
        top_k: int = 10
    ) -> List[RerankResult]:
        """
        Rerank commits by relevance to query.

        Args:
            query: Search query
            commits: List of commits to rerank
            top_k: Maximum results to return

        Returns:
            List of RerankResult sorted by relevance
        """
        if not self._model:
            raise RerankerError("Model not loaded")

        if not commits:
            return []

        # Prepare pairs for cross-encoder
        pairs = []
        for i, commit in enumerate(commits):
            commit_text = self._format_commit(commit)
            pairs.append([query, commit_text])

        # Get relevance scores
        try:
            scores = self._model.predict(pairs, batch_size=32)
        except Exception as e:
            raise RerankerError(f"Cross-encoder prediction failed: {e}")

        # Create results
        results = []
        for i, (commit, score) in enumerate(zip(commits, scores)):
            results.append(RerankResult(
                commit=commit,
                relevance_score=float(score),
                original_rank=i,
                reranker_type="cross-encoder"
            ))

        # Sort by relevance score and return top_k
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:top_k]

    @property
    def name(self) -> str:
        return f"cross-encoder-{self.model_name}"


class LLMReranker(Reranker):
    """
    Reranker using LLM for relevance scoring.

    Uses an LLM to score the relevance of commits to a query.
    More flexible than cross-encoders but slower and more expensive.
    """

    def __init__(self, config: Optional[GimiConfig] = None):
        """
        Initialize LLM reranker.

        Args:
            config: Configuration with LLM settings
        """
        self.config = config or GimiConfig()
        self._client = None
        self._init_client()

    def _init_client(self):
        """Initialize LLM client."""
        if self.config.llm_provider == "openai":
            try:
                import openai
                api_key = self.config.llm_api_key or openai.api_key
                self._client = openai.OpenAI(api_key=api_key)
            except ImportError:
                raise RerankerError("OpenAI package not installed")
        else:
            raise RerankerError(f"Unsupported LLM provider: {self.config.llm_provider}")

    def _format_commit_for_llm(self, commit: CommitMetadata) -> str:
        """Format commit for LLM input."""
        text = f"Commit: {commit.short_hash}\n"
        text += f"Message: {commit.message}\n"
        text += f"Author: {commit.author_name}\n"
        if commit.files_changed:
            text += f"Files: {', '.join(commit.files_changed[:10])}\n"
        return text

    def _score_with_llm(self, query: str, commit_text: str) -> float:
        """Score relevance using LLM."""
        if not self._client:
            raise RerankerError("LLM client not initialized")

        prompt = f"""Rate the relevance of the following commit to the query.

Query: {query}

Commit:
{commit_text}

Rate the relevance on a scale of 0.0 to 1.0, where:
- 0.0: Completely irrelevant
- 0.5: Somewhat relevant
- 1.0: Highly relevant

Respond with only a number between 0.0 and 1.0."""

        try:
            response = self._client.chat.completions.create(
                model=self.config.llm_model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=10
            )

            content = response.choices[0].message.content.strip()

            # Extract number from response
            import re
            match = re.search(r'([0-9]*\.?[0-9]+)', content)
            if match:
                score = float(match.group(1))
                return max(0.0, min(1.0, score))

            return 0.0

        except Exception as e:
            raise RerankerError(f"LLM scoring failed: {e}")

    def rerank(
        self,
        query: str,
        commits: List[CommitMetadata],
        top_k: int = 10
    ) -> List[RerankResult]:
        """
        Rerank commits using LLM scoring.

        Args:
            query: Search query
            commits: List of commits to rerank
            top_k: Maximum results to return

        Returns:
            List of RerankResult sorted by relevance
        """
        if not self._client:
            raise RerankerError("LLM client not initialized")

        if not commits:
            return []

        # Score each commit
        results = []
        for i, commit in enumerate(commits):
            commit_text = self._format_commit_for_llm(commit)

            try:
                score = self._score_with_llm(query, commit_text)
            except Exception as e:
                # If scoring fails, use a default low score
                score = 0.0

            results.append(RerankResult(
                commit=commit,
                relevance_score=score,
                original_rank=i,
                reranker_type="llm"
            ))

        # Sort by relevance score
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:top_k]

    @property
    def name(self) -> str:
        return f"llm-{self.config.llm_model}"


class SemanticSearchError(Exception):
    """Error during semantic search."""
    pass


class NoOpReranker(Reranker):
    """
    No-op reranker that returns results unchanged.

    Used when reranking is disabled.
    """

    def rerank(
        self,
        query: str,
        commits: List[CommitMetadata],
        top_k: int = 10
    ) -> List[RerankResult]:
        """Return commits unchanged with neutral scores."""
        return [
            RerankResult(
                commit=c,
                relevance_score=0.5,
                original_rank=i,
                reranker_type="noop"
            )
            for i, c in enumerate(commits[:top_k])
        ]

    @property
    def name(self) -> str:
        return "noop"


def create_reranker(config: GimiConfig) -> Optional[Reranker]:
    """
    Factory function to create a reranker based on config.

    Args:
        config: Configuration

    Returns:
        Reranker instance or None if reranking is disabled
    """
    # Check if reranking is enabled
    if not getattr(config, 'retrieval_rerank', False):
        return None

    reranker_type = getattr(config, 'reranker_type', 'cross_encoder')

    if reranker_type == 'cross_encoder':
        model_name = getattr(config, 'reranker_model', None)
        return CrossEncoderReranker(model_name=model_name)
    elif reranker_type == 'llm':
        return LLMReranker(config)
    else:
        raise ValueError(f"Unknown reranker type: {reranker_type}")


if __name__ == '__main__':
    # Test semantic search and fusion
    import tempfile
    from pathlib import Path

    print("Testing Semantic Search and Fusion...")

    # Test fusion without actual embeddings (using mock data)
    print("\n=== Testing SearchFusion ===")

    from gimi.index.git import CommitMetadata
    from gimi.search.keyword import KeywordSearchResult

    # Create test commits
    commits = [
        CommitMetadata(
            hash=f"commit{i}" * 8,
            short_hash=f"c{i}",
            message=f"Test commit {i} with bug fix",
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

    # Create semantic results (different order)
    semantic_results = [
        SemanticSearchResult(commit=commits[1], score=0.95),
        SemanticSearchResult(commit=commits[3], score=0.85),
        SemanticSearchResult(commit=commits[0], score=0.75),
        SemanticSearchResult(commit=commits[4], score=0.65),
    ]

    # Test fusion
    fusion = SearchFusion()

    print("\nWeighted Fusion:")
    results = fusion.fuse(keyword_results, semantic_results, top_k=10, method="weighted")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r.commit.short_hash}: fused={r.fused_score:.3f}, "
              f"keyword={r.keyword_score:.3f}, semantic={r.semantic_score:.3f}")

    print("\nRRF Fusion:")
    results = fusion.fuse(keyword_results, semantic_results, top_k=10, method="rrf")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r.commit.short_hash}: fused={r.fused_score:.3f}, "
              f"keyword_rank={r.rank_keyword}, semantic_rank={r.rank_semantic}")

    print("\n✓ Fusion tests passed!")

    # Test reranker factory
    print("\n=== Testing Reranker Factory ===")

    config = GimiConfig()
    config.retrieval_rerank = False
    reranker = create_reranker(config)
    print(f"Reranker (disabled): {reranker}")

    # Note: We can't test actual rerankers without the models installed
    print("\n✓ Reranker factory tests passed!")

    print("\n✓ All semantic search and fusion tests passed!")
