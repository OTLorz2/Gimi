"""CLI entry point for Gimi - the auxiliary programming agent.

This module provides the main entry point for the Gimi CLI tool.
It handles argument parsing, repository discovery, and orchestrates
the full flow from user query to LLM-generated suggestions.
"""

import argparse
import sys
import os
from typing import Optional, List, Dict, Any

from gimi.core.repo import find_repo_root, get_gimi_dir, ensure_gimi_structure
from gimi.core.lock import acquire_lock, release_lock
from gimi.core.config import load_config, Config
from gimi.core.refs import load_refs_snapshot, save_refs_snapshot, get_current_refs, are_refs_consistent
from gimi.index.git import traverse_commits, get_commit_metadata
from gimi.index.writer import IndexWriter
from gimi.index.vector import VectorIndex
from gimi.index.checkpoint import CheckpointManager
from gimi.retrieval.keywords import KeywordSearcher
from gimi.retrieval.semantic import SemanticSearcher
from gimi.retrieval.fusion import FusionRanker
from gimi.retrieval.rerank import Reranker
from gimi.context.diff import DiffFetcher
from gimi.context.prompt import PromptBuilder
from gimi.llm.client import LLMClient
from gimi.llm.output import OutputFormatter
from gimi.observability.logging import RequestLogger


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
        return repo_root
    except Exception as e:
        print(f"Error finding repository root: {e}", file=sys.stderr)
        sys.exit(1)


def build_index_if_needed(
    repo_root: str,
    gimi_dir: str,
    config: Config,
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
    index_dir = os.path.join(gimi_dir, 'index')
    vectors_dir = os.path.join(gimi_dir, 'vectors')

    # Check if we need to build the index
    index_exists = os.path.exists(index_dir) and os.listdir(index_dir)

    if index_exists and not force_rebuild:
        # Check if index is still valid
        snapshot = load_refs_snapshot(gimi_dir)
        if snapshot:
            current_refs = get_current_refs(repo_root)
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
        # Initialize checkpoint manager
        checkpoint_mgr = CheckpointManager(gimi_dir)

        # Get branches to index
        branches = config.get('index_branches', ['HEAD'])

        # Create index writer
        index_writer = IndexWriter(index_dir)

        # Create vector index (if embedding is available)
        vector_index = None
        try:
            vector_index = VectorIndex(vectors_dir)
        except Exception as e:
            if verbose:
                print(f"Warning: Could not initialize vector index: {e}")

        # Traverse commits and build index
        total_commits = 0
        for branch in branches:
            if verbose:
                print(f"  Indexing branch: {branch}")

            for commit_data in traverse_commits(repo_root, branch, limit=config.get('max_commits')):
                # Write to lightweight index
                index_writer.write_commit(commit_data)

                # Write to vector index if available
                if vector_index:
                    vector_index.add_commit(commit_data)

                total_commits += 1

                # Checkpoint periodically
                if total_commits % 100 == 0:
                    checkpoint_mgr.save_checkpoint(branch, commit_data['hash'])

        # Finalize indexes
        index_writer.close()
        if vector_index:
            vector_index.close()

        # Update refs snapshot
        current_refs = get_current_refs(repo_root)
        save_refs_snapshot(gimi_dir, current_refs)

        if verbose:
            print(f"Index built successfully with {total_commits} commits")

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
    gimi_dir = get_gimi_dir(repo_root)

    # Ensure .gimi structure exists
    ensure_gimi_structure(repo_root)

    # Load configuration
    config = load_config(gimi_dir)

    # Override config with CLI args
    if args.top_k:
        config.set('top_k', args.top_k)

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
            gimi_dir=gimi_dir,
            config=config,
            force_rebuild=args.rebuild_index,
            verbose=args.verbose
        ):
            print("Error: Failed to build or update index.", file=sys.stderr)
            return 1

        # Initialize retrieval components
        index_dir = os.path.join(gimi_dir, 'index')
        vectors_dir = os.path.join(gimi_dir, 'vectors')

        keyword_searcher = KeywordSearcher(index_dir)
        semantic_searcher = SemanticSearcher(vectors_dir)
        fusion_ranker = FusionRanker()
        reranker = Reranker() if config.get('use_reranker', False) else None

        # Stage 1: Keyword and path retrieval
        if args.verbose:
            print("Searching for relevant commits...")

        candidates = keyword_searcher.search(
            query=args.query,
            file_path=args.file_path,
            branch=args.branch,
            limit=config.get('candidate_limit', 100)
        )

        if args.verbose:
            print(f"  Found {len(candidates)} candidates via keyword search")

        # Stage 2: Semantic retrieval and fusion
        if semantic_searcher.is_available():
            semantic_results = semantic_searcher.search(
                query=args.query,
                candidate_hashes=[c['hash'] for c in candidates],
                limit=config.get('top_k', 25)
            )

            top_commits = fusion_ranker.fuse(
                keyword_results=candidates,
                semantic_results=semantic_results,
                top_k=config.get('top_k', 25)
            )
        else:
            top_commits = candidates[:config.get('top_k', 25)]

        if args.verbose:
            print(f"  Selected top {len(top_commits)} commits after fusion")

        # Stage 3: Optional reranking
        if reranker and reranker.is_available():
            if args.verbose:
                print("Reranking commits...")
            top_commits = reranker.rerank(
                query=args.query,
                commits=top_commits,
                top_k=config.get('final_top_k', 10)
            )
            if args.verbose:
                print(f"  Final selection: {len(top_commits)} commits")

        # Fetch diffs for top commits
        if args.verbose:
            print("Fetching diffs...")

        diff_fetcher = DiffFetcher(repo_root, cache_dir=os.path.join(gimi_dir, 'cache'))
        diffs = []

        for commit in top_commits:
            diff_data = diff_fetcher.fetch(
                commit_hash=commit['hash'],
                max_files=config.get('max_files_per_commit', 10),
                max_lines_per_file=config.get('max_lines_per_file', 100)
            )
            diffs.append({
                'commit': commit,
                'diff': diff_data
            })

        if args.verbose:
            print(f"  Fetched diffs for {len(diffs)} commits")

        # Build prompt and call LLM
        if args.verbose:
            print("Generating suggestions...")

        prompt_builder = PromptBuilder()
        prompt = prompt_builder.build(
            query=args.query,
            diffs=diffs,
            file_path=args.file_path
        )

        llm_client = LLMClient(config)
        response = llm_client.generate(prompt)

        # Format and output results
        output_formatter = OutputFormatter()
        formatted_output = output_formatter.format(
            response=response,
            referenced_commits=[d['commit'] for d in diffs]
        )

        print(formatted_output)

        # Log the request
        logger.end_request(
            request_id=request_id,
            success=True,
            candidate_count=len(candidates),
            top_k=len(top_commits),
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
