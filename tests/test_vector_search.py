"""Tests for vector search integration (T8)."""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, MagicMock

from gimi.retrieval.hybrid_search import HybridSearcher, SearchResult
from gimi.indexing.git_collector import CommitMetadata
from gimi.index.embeddings import MockEmbeddingProvider


@pytest.fixture
def mock_lightweight_index():
    """Create a mock lightweight index."""
    index = Mock()

    # Mock commit data
    commits = [
        CommitMetadata(
            hash="abc123",
            message="Fix bug in authentication",
            author="John Doe",
            author_email="john@example.com",
            timestamp=1609459200,
            branch="main",
            changed_files=["src/auth.py", "src/login.py"],
            insertions=10,
            deletions=5,
            parent_hashes=["def456"],
        ),
        CommitMetadata(
            hash="ghi789",
            message="Add new feature for user dashboard",
            author="Jane Smith",
            author_email="jane@example.com",
            timestamp=1609545600,
            branch="main",
            changed_files=["src/dashboard.py", "src/user.py"],
            insertions=50,
            deletions=10,
            parent_hashes=["abc123"],
        ),
    ]

    index.get_commit_by_hash = Mock(side_effect=lambda h: next(
        (c for c in commits if c.hash == h), None
    ))
    index.search_by_keyword = Mock(return_value=commits)
    index.search_by_path = Mock(return_value=commits)

    return index


@pytest.fixture
def mock_vector_index():
    """Create a mock vector index."""
    index = Mock()
    index.search = Mock(return_value=[
        ("abc123", 0.95),
        ("ghi789", 0.85),
    ])
    return index


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    provider = MockEmbeddingProvider(dimension=384)
    return provider


class TestHybridSearcherWithVectorSearch:
    """Test hybrid searcher with vector search integration."""

    def test_search_without_vector_index(self, mock_lightweight_index):
        """Test that search works without vector index (graceful degradation)."""
        searcher = HybridSearcher(
            lightweight_index=mock_lightweight_index,
            vector_index=None,
            embedding_provider=None,
            enable_vector_search=True,
        )

        results = searcher.search("authentication bug", top_k=5)

        assert len(results) > 0
        # Should still get results from keyword search
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_with_vector_index(
        self,
        mock_lightweight_index,
        mock_vector_index,
        mock_embedding_provider,
    ):
        """Test search with vector index integration."""
        searcher = HybridSearcher(
            lightweight_index=mock_lightweight_index,
            vector_index=mock_vector_index,
            embedding_provider=mock_embedding_provider,
            enable_vector_search=True,
        )

        results = searcher.search("authentication bug", top_k=5)

        # Vector search should have been called
        mock_vector_index.search.assert_called_once()

        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)

    def test_vector_search_disabled(
        self,
        mock_lightweight_index,
        mock_vector_index,
        mock_embedding_provider,
    ):
        """Test that vector search can be disabled."""
        searcher = HybridSearcher(
            lightweight_index=mock_lightweight_index,
            vector_index=mock_vector_index,
            embedding_provider=mock_embedding_provider,
            enable_vector_search=False,  # Disabled
        )

        results = searcher.search("authentication bug", top_k=5)

        # Vector search should NOT have been called
        mock_vector_index.search.assert_not_called()

        assert len(results) > 0

    def test_vector_search_error_handling(
        self,
        mock_lightweight_index,
        mock_vector_index,
        mock_embedding_provider,
    ):
        """Test that vector search errors are handled gracefully."""
        # Make vector search raise an exception
        mock_vector_index.search.side_effect = Exception("Vector DB error")

        searcher = HybridSearcher(
            lightweight_index=mock_lightweight_index,
            vector_index=mock_vector_index,
            embedding_provider=mock_embedding_provider,
            enable_vector_search=True,
        )

        # Should not raise exception, should fall back to other search methods
        results = searcher.search("authentication bug", top_k=5)

        # Should still get results from keyword/path search
        assert len(results) > 0
