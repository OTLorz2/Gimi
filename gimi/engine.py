"""
Gimi Query Engine - Integrates retrieval and LLM for answering queries.

This module provides the main query processing pipeline that:
1. Validates index status
2. Performs hybrid search for relevant commits
3. Builds context from commit diffs
4. Generates prompts and calls LLM
5. Returns formatted responses
"""

import sys
from pathlib import Path
from typing import List, Optional, Callable
from dataclasses import dataclass

from gimi.core.config import load_config, GimiConfig
from gimi.core.validation import validate_index, IndexStatus
from gimi.core.repo import find_repo_root
from gimi.indexing.lightweight_index import LightweightIndex
from gimi.index.vector_index import VectorIndex
from gimi.index.embeddings import get_embedding_provider
from gimi.retrieval.hybrid_search import HybridSearcher, SearchResult
from gimi.context.diff_manager import DiffManager
from gimi.llm.client import create_llm_client, LLMResponse
from gimi.llm.prompt_builder import PromptBuilder, PromptResult


@dataclass
class QueryResult:
    """Result of processing a query."""
    answer: str
    referenced_commits: List[str]
    context_tokens: int
    latency_ms: float


class QueryEngineError(Exception):
    """Raised when query processing fails."""
    pass


class QueryEngine:
    """
    Main query processing engine for Gimi.

    Integrates all components to provide end-to-end query answering.
    """

    def __init__(
        self,
        repo_root: Path,
        gimi_dir: Path,
        config: Optional[GimiConfig] = None,
        progress_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the query engine.

        Args:
            repo_root: Root of the git repository
            gimi_dir: Path to .gimi directory
            config: Gimi configuration (loaded from file if not provided)
            progress_callback: Optional callback for progress updates
        """
        self.repo_root = Path(repo_root)
        self.gimi_dir = Path(gimi_dir)
        self.config = config or load_config(self.gimi_dir)
        self.progress_callback = progress_callback

        # Initialize components
        self._searcher: Optional[HybridSearcher] = None
        self._diff_manager: Optional[DiffManager] = None
        self._prompt_builder: Optional[PromptBuilder] = None
        self._llm_client: Optional[Any] = None

    def _report_progress(self, message: str) -> None:
        """Report progress if callback is set."""
        if self.progress_callback:
            self.progress_callback(message)

    def validate(self) -> IndexStatus:
        """
        Validate that the index is ready for querying.

        Returns:
            IndexStatus indicating the state of the index
        """
        return validate_index(self.repo_root, self.gimi_dir)

    def initialize(self) -> None:
        """
        Initialize all components for querying.

        This must be called after validation passes.
        """
        self._report_progress("Initializing search components...")

        # Initialize searcher with indexes
        index_dir = self.gimi_dir / "index"
        vector_dir = self.gimi_dir / "vectors"

        lw_index = LightweightIndex(index_dir)
        lw_index.initialize()

        # Initialize vector index if available
        vector_index = None
        embedding_provider = None
        if vector_dir.exists():
            try:
                vector_index = VectorIndex(vector_dir)
                vector_index.initialize()
                embedding_provider = get_embedding_provider(self.config.index)
            except Exception as e:
                self._report_progress(f"Vector index not available: {e}")

        self._searcher = HybridSearcher(
            lightweight_index=lw_index,
            vector_index=vector_index,
            embedding_provider=embedding_provider,
            keyword_weight=0.3,
            path_weight=0.3,
            vector_weight=0.4,
            use_rrf=True,
            enable_vector_search=vector_index is not None
        )

        # Initialize diff manager
        self._diff_manager = DiffManager(
            repo_root=self.repo_root,
            config=self.config.context.truncate
        )

        # Initialize prompt builder
        self._prompt_builder = PromptBuilder(
            max_context_tokens=self.config.context.max_tokens
        )

        # Initialize LLM client
        self._llm_client = create_llm_client(self.config.llm)

        self._report_progress("Components initialized successfully")

    def query(self, query: str, file_path: Optional[str] = None) -> QueryResult:
        """
        Process a user query and return an answer.

        Args:
            query: The user's query
            file_path: Optional file path to filter results

        Returns:
            QueryResult containing the answer and metadata

        Raises:
            QueryEngineError: If query processing fails
        """
        import time
        start_time = time.time()

        # Validate index
        status = self.validate()
        if not status.is_valid:
            raise QueryEngineError(
                f"Index is not ready: {status.message}. "
                "Please run 'gimi index' to build the index."
            )

        # Initialize if needed
        if self._searcher is None:
            self.initialize()

        try:
            # 1. Search for relevant commits
            self._report_progress("Searching for relevant commits...")
            search_results = self._searcher.search(
                query=query,
                file_path=file_path,
                top_k=self.config.retrieval.top_k
            )

            if not search_results:
                return QueryResult(
                    answer="I couldn't find any relevant commits for your query. "
                           "Try rephrasing your question or check if the repository has relevant history.",
                    referenced_commits=[],
                    context_tokens=0,
                    latency_ms=(time.time() - start_time) * 1000
                )

            # 2. Build context from diffs
            self._report_progress("Building context from commit diffs...")
            diff_results = []
            for result in search_results:
                commit_diff = self._diff_manager.build_commit_diff(result.commit.hash)
                if commit_diff:
                    diff_results.append(commit_diff)

            # 3. Build prompt
            prompt_result = self._prompt_builder.build_prompt(
                query=query,
                diff_results=diff_results,
                max_commits=self.config.retrieval.top_k
            )

            # 4. Call LLM
            self._report_progress("Generating response...")
            llm_response = self._llm_client.complete(
                messages=prompt_result.to_messages(),
                temperature=self.config.llm.temperature,
                max_tokens=self.config.llm.max_tokens
            )

            latency_ms = (time.time() - start_time) * 1000

            return QueryResult(
                answer=llm_response.content,
                referenced_commits=prompt_result.referenced_commits,
                context_tokens=prompt_result.context_tokens,
                latency_ms=latency_ms
            )

        except Exception as e:
            raise QueryEngineError(f"Query processing failed: {e}")


def create_engine(
    repo_root: Optional[Path] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> QueryEngine:
    """
    Create and initialize a QueryEngine.

    This is a convenience factory function that handles:
    1. Finding the repo root if not provided
    2. Loading configuration
    3. Creating the engine instance

    Args:
        repo_root: Optional path to repo root (will be auto-discovered if not provided)
        progress_callback: Optional callback for progress updates

    Returns:
        Initialized QueryEngine instance

    Raises:
        QueryEngineError: If engine creation fails
    """
    try:
        if repo_root is None:
            repo_root = find_repo_root()

        gimi_dir = repo_root / ".gimi"
        config = load_config(gimi_dir)

        return QueryEngine(
            repo_root=repo_root,
            gimi_dir=gimi_dir,
            config=config,
            progress_callback=progress_callback
        )
    except Exception as e:
        raise QueryEngineError(f"Failed to create query engine: {e}")
