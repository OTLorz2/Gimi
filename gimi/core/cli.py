"""CLI entry point for Gimi - the auxiliary programming agent.

This module provides the main entry point for the Gimi CLI tool.
It handles argument parsing, repository discovery, and orchestrates
the full flow from user query to LLM-generated suggestions.
"""

import argparse
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from gimi.core.repo import find_repo_root, get_gimi_dir, ensure_gimi_structure
from gimi.core.lock import acquire_lock, release_lock
from gimi.core.config import load_config, GimiConfig
from gimi.core.refs import (
    load_refs_snapshot,
    save_refs_snapshot,
    get_current_refs,
    are_refs_consistent
)
from gimi.index.builder import IndexBuilder
from gimi.index.lightweight import LightweightIndex
from gimi.index.vector_index import VectorIndex
from gimi.index.embeddings import get_embedding_provider
from gimi.retrieval.engine import RetrievalEngine
from gimi.observability.logging import RequestLogger, IndexBuildLogger


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog='gimi',
        description='Gimi - An auxiliary programming agent that analyzes git history to provide code suggestions.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  gimi "How do I implement error handling in this module?"
  gimi "Explain the authentication flow" --file src/auth.py
  gimi "What changed in the API recently?" --branch main
        '''
    )

    parser.add_argument(
        'query',
        type=str,
        help='Your question or request for code suggestions'
    )

    parser.add_argument(
        '--file', '-f',
        type=str,
        dest='file_path',
        help='Specific file to focus the analysis on'
    )

    parser.add_argument(
        '--branch', '-b',
        type=str,
        dest='branch',
        help='Specific branch to analyze (default: current branch)'
    )

    parser.add_argument(
        '--rebuild-index',
        action='store_true',
        help='Force rebuild of the commit index'
    )

    parser.add_argument(
        '--top-k',
        type=int,
        default=None,
        help='Number of top commits to retrieve (overrides config)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    return parser


def validate_environment() -> str:
    """Validate that we're in a git repository.

    Returns:
        str: The repository root path

    Raises:
        SystemExit: If not in a git repository
    """
    try:
        repo_root = find_repo_root()
        if not repo_root:
            print("Error: Not a git repository. Please run gimi inside a git repository.", file=sys.stderr)
            sys.exit(1)
        return str(repo_root)
    except Exception as e:
        print(f"Error finding repository root: {e}", file=sys.stderr)
        sys.exit(1)


def build_index_if_needed(
    repo_root: str,
    gimi_dir: str,
    config: GimiConfig,
    force_rebuild: bool = False,
    verbose: bool = False
) -> bool:
    """Build or update the commit index if needed.

    Args:
        repo_root: Path to the repository root
        gimi_dir: Path to the .gimi directory
        config: Loaded configuration
        force_rebuild: Whether to force a full rebuild
        verbose: Whether to print verbose output

    Returns:
        bool: True if index is ready, False otherwise
    """
    from pathlib import Path

    gimi_path = Path(gimi_dir)
    index_dir = gimi_path / 'index'
    vectors_dir = gimi_path / 'vectors'

    # Check if we need to build the index
    index_exists = index_dir.exists() and any(index_dir.iterdir())

    if index_exists and not force_rebuild:
        # Check if index is still valid
        snapshot = load_refs_snapshot(gimi_path)
        if snapshot:
            current_refs = get_current_refs(Path(repo_root))
            if are_refs_consistent(snapshot, current_refs):
                if verbose:
                    print("Using existing index (refs match)")
                return True
            else:
                if verbose:
                    print("Index is outdated (refs changed), rebuilding...")
        else:
            if verbose:
                print("No refs snapshot found, rebuilding...")

    # Build the index
    if verbose:
        print("Building commit index...")

    try:
        # Initialize index builder
        builder = IndexBuilder(
            repo_root=Path(repo_root),
            gimi_dir=gimi_path,
            config=config.index
        )

        # Build index
        builder.build(incremental=not force_rebuild)

        if verbose:
            print(f"Index built successfully")

        return True

    except Exception as e:
        print(f"Error building index: {e}", file=sys.stderr)
        return False


def main() -> int:
    """Main entry point for the CLI.

    Returns:
        int: Exit code (0 for success, non-zero for errors)
    """
    # Parse arguments
    parser = create_parser()
    args = parser.parse_args()

    # Validate environment
    repo_root = validate_environment()

    # Get .gimi directory
    gimi_dir = get_gimi_dir(Path(repo_root))

    # Ensure .gimi structure exists
    ensure_gimi_structure(Path(repo_root))

    # Load configuration
    config = load_config(gimi_dir)

    # Override config with CLI args
    if args.top_k:
        config.set('retrieval.top_k', args.top_k)

    # Acquire lock for write operations
    lock_file = os.path.join(gimi_dir, '.lock')
    if not acquire_lock(lock_file):
        print("Error: Could not acquire lock. Another gimi process may be running.", file=sys.stderr)
        return 1

    try:
        # Initialize request logger
        logger = RequestLogger(gimi_dir)
        request_id = logger.start_request(
            repo_root=repo_root,
            query=args.query,
            file_path=args.file_path,
            branch=args.branch
        )

        # Build index if needed
        if not build_index_if_needed(
            repo_root=repo_root,
            gimi_dir=str(gimi_dir),
            config=config,
            force_rebuild=args.rebuild_index,
            verbose=args.verbose
        ):
            print("Error: Failed to build or update index.", file=sys.stderr)
            return 1

        # Initialize retrieval engine
        index_dir = gimi_dir / 'index'
        vectors_dir = gimi_dir / 'vectors'

        # Get embedding provider
        embedding_provider = get_embedding_provider(config.index)

        # Initialize retrieval engine
        with LightweightIndex(index_dir) as lightweight_index:
            lightweight_index.initialize()

            with VectorIndex(vectors_dir) as vector_index:
                vector_index.initialize()

                retrieval_engine = RetrievalEngine(
                    lightweight_index=lightweight_index,
                    vector_index=vector_index,
                    embedding_provider=embedding_provider,
                    config=config.retrieval
                )

                # Perform search
                if args.verbose:
                    print("Searching for relevant commits...")

                file_paths = [args.file_path] if args.file_path else None
                results = retrieval_engine.search(
                    query=args.query,
                    file_paths=file_paths
                )

                if args.verbose:
                    print(f"  Found {len(results)} relevant commits")

                # Get diffs for top results
                from gimi.context.diff_manager import DiffManager

                diff_manager = DiffManager(
                    repo_root=Path(repo_root),
                    cache_dir=gimi_dir / 'cache'
                )

                diffs = []
                for result in results[:config.retrieval.top_k]:
                    diff = diff_manager.get_diff(
                        commit_hash=result.commit.hash,
                        commit_message=result.commit.message,
                        author=result.commit.author,
                        author_date=result.commit.date.isoformat() if hasattr(result.commit, 'date') else ""
                    )
                    diffs.append({
                        'commit': result.commit,
                        'diff': diff
                    })

                if args.verbose:
                    print(f"  Fetched diffs for {len(diffs)} commits")

                # Call LLM
                if args.verbose:
                    print("Generating suggestions...")

                from gimi.llm.client import OpenAIClient, AnthropicClient
                from gimi.llm.prompt_builder import PromptBuilder

                prompt_builder = PromptBuilder(config.llm.max_context_tokens)
                diff_results = []
                for d in diffs:
                    diff_obj = d['diff']  # This is already a DiffResult
                    diff_results.append(diff_obj)
                prompt = prompt_builder.build_prompt(
                    query=args.query,
                    diff_results=diff_results
                )

                # Initialize LLM client based on provider
                if config.llm.provider == "openai":
                    llm_client = OpenAIClient(
                        api_key=config.llm.api_key,
                        model=config.llm.model,
                        api_base=config.llm.api_base,
                        timeout=config.llm.timeout
                    )
                elif config.llm.provider == "anthropic":
                    llm_client = AnthropicClient(
                        api_key=config.llm.api_key,
                        model=config.llm.model,
                        api_base=config.llm.api_base,
                        timeout=config.llm.timeout
                    )
                else:
                    raise ValueError(f"Unknown LLM provider: {config.llm.provider}")

                messages = prompt.to_messages()
                llm_response = llm_client.complete(
                    messages=messages,
                    temperature=config.llm.temperature,
                    max_tokens=config.llm.max_tokens
                )
                response = {
                    'text': llm_response.content,
                    'duration': llm_response.latency_ms / 1000
                }

                # Output results
                print()
                print("=" * 60)
                print("Gimi Suggestion")
                print("=" * 60)
                print()
                print(response.get('text', 'No response generated.'))
                print()
                print("-" * 60)
                print(f"Referenced {len(diffs)} commits:")
                for d in diffs:
                    commit = d['commit']
                    print(f"  - {commit.hash[:7]}: {commit.message[:50]}...")
                print("-" * 60)

                # Log the request
                logger.end_request(
                    request_id=request_id,
                    success=True,
                    candidate_count=len(results),
                    top_k=len(diffs),
                    diff_count=len(diffs),
                    llm_duration=response.get('duration', 0)
                )

        return 0

    except KeyboardInterrupt:
        print("\nOperation cancelled by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()

        # Log the error
        try:
            if 'logger' in locals() and 'request_id' in locals():
                logger.end_request(
                    request_id=request_id,
                    success=False,
                    error=str(e)
                )
        except:
            pass

        return 1
    finally:
        # Release lock
        try:
            if 'lock_file' in locals():
                release_lock(lock_file)
        except:
            pass


if __name__ == '__main__':
    sys.exit(main())
