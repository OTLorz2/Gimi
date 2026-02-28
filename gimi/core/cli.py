"""CLI entry point and argument parsing for Gimi."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from gimi.core.repo import find_repo_root, ensure_gimi_structure, RepoError
from gimi.core.lock import LockError
from gimi.core.config import init_config, ConfigError
from gimi.core.refs import check_index_validity


class CLIError(Exception):
    """Raised for CLI-related errors."""
    pass


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="gimi",
        description="Gimi - An auxiliary programming agent for git repositories.",
        epilog="Example: gimi 'How do I fix this bug?' --file src/main.py --branch main"
    )

    # Positional argument for user query/requirement
    parser.add_argument(
        "query",
        nargs="?",
        help="Your question or requirement (e.g., 'How to implement X?')"
    )

    # Optional arguments
    parser.add_argument(
        "--file", "-f",
        action="append",
        dest="files",
        help="Specify file(s) to focus on (can be used multiple times)"
    )

    parser.add_argument(
        "--branch", "-b",
        help="Specify branch to search (default: current branch)"
    )

    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Force rebuild of the commit index"
    )

    parser.add_argument(
        "--config",
        help="Path to custom config file"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version="%(prog)s 0.1.0"
    )

    return parser


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command line arguments.

    Args:
        args: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Parsed arguments namespace
    """
    parser = create_parser()
    return parser.parse_args(args)


def validate_args(parsed: argparse.Namespace) -> None:
    """
    Validate parsed arguments.

    Args:
        parsed: Parsed arguments namespace

    Raises:
        CLIError: If validation fails
    """
    # Currently query is optional to allow for commands like --version
    # In future iterations, query may become required for the main flow
    pass


def main(args: Optional[List[str]] = None) -> int:
    """
    Main entry point for the CLI.

    Args:
        args: Command line arguments

    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    try:
        # Parse arguments
        parsed = parse_args(args)
        validate_args(parsed)

        # Find repository root
        repo_root = find_repo_root()

        # Ensure .gimi directory structure exists
        gimi_dir = ensure_gimi_structure(repo_root)

        # T4: Load or initialize configuration
        config = init_config(gimi_dir)

        # T5: Check index validity
        is_valid, current_refs, saved_refs = check_index_validity(gimi_dir, repo_root)

        # Determine if we need to rebuild index
        needs_rebuild = parsed.rebuild_index or not is_valid

        # Build or update index if needed
        if needs_rebuild:
            from gimi.index.builder import IndexBuilder
            from gimi.core.lock import GimiLock

            with GimiLock(gimi_dir) as lock:
                builder = IndexBuilder(repo_root, gimi_dir, config.index)

                def progress(msg, current, total):
                    pct = (current / total * 100) if total > 0 else 0
                    print(f"  {msg}: {current}/{total} ({pct:.1f}%)")

                builder.set_progress_callback(progress)
                builder.build(incremental=True)

            # Re-check validity after build
            is_valid, _, _ = check_index_validity(gimi_dir, repo_root)
            print(f"\nIndex built successfully. Valid: {is_valid}")

        # Skip full flow if no query provided
        if not parsed.query:
            print("\nNo query provided. Use --help for usage information.")
            return 0

        # Initialize logger
        from gimi.core.logging import GimiLogger
        logger = GimiLogger(gimi_dir / "logs")

        # Log the start of the request
        logger.log_info(f"Processing query: {parsed.query}")

        # Initialize embedding provider and retrieval engine
        from gimi.index.embeddings import get_embedding_provider
        from gimi.index.lightweight import LightweightIndex
        from gimi.index.vector_index import VectorIndex
        from gimi.retrieval.engine import RetrievalEngine

        embedding_provider = get_embedding_provider(config.index)
        lightweight_index = LightweightIndex(gimi_dir / "index")
        vector_index = VectorIndex(gimi_dir / "vectors")

        retrieval_engine = RetrievalEngine(
            lightweight_index=lightweight_index,
            vector_index=vector_index,
            embedding_provider=embedding_provider,
            config=config.retrieval
        )

        # T10-T12: Retrieve relevant commits
        print(f"\nSearching for relevant commits...")
        results = retrieval_engine.search(
            query=parsed.query,
            file_paths=parsed.files,
            progress_callback=lambda msg, curr, total: print(f"  {msg}: {curr}/{total}")
        )

        if not results:
            print("\nNo relevant commits found.")
            logger.log_request(
                repo_root=str(repo_root),
                query=parsed.query,
                index_valid=is_valid,
                index_rebuilt=needs_rebuild,
                candidate_count=0,
                top_k_count=0,
                context_tokens=0,
                llm_model=config.llm.model,
                llm_latency_ms=0.0,
                response_status="no_results",
                files_specified=parsed.files,
                branch_specified=parsed.branch
            )
            return 0

        print(f"\nFound {len(results)} relevant commits.")

        # T13: Get diffs for top commits
        from gimi.context.diff_manager import DiffManager, TruncationConfig

        truncation_config = TruncationConfig(
            max_files_per_commit=config.context.max_files_per_commit,
            max_lines_per_file=config.context.max_lines_per_file,
            max_total_lines=config.context.max_total_tokens // 10  # Rough estimate
        )

        diff_manager = DiffManager(
            repo_root=repo_root,
            cache_dir=gimi_dir / "cache",
            config=truncation_config
        )

        print("\nFetching commit diffs...")
        diff_results = []
        for i, result in enumerate(results[:config.retrieval.top_k], 1):
            commit = result.commit
            print(f"  [{i}/{min(config.retrieval.top_k, len(results))}] {commit.hash[:7]}: {commit.message[:50]}...")
            diff_result = diff_manager.get_diff(
                commit_hash=commit.hash,
                commit_message=commit.message,
                author=commit.author,
                author_date=commit.author_date
            )
            diff_results.append(diff_result)

        # T14-T15: Build prompt and call LLM
        from gimi.llm.prompt_builder import PromptBuilder
        from gimi.llm.client import OpenAIClient, AnthropicClient, LLMError

        print(f"\nGenerating response using {config.llm.provider} ({config.llm.model})...")

        prompt_builder = PromptBuilder(max_context_tokens=config.context.max_total_tokens)
        prompt_result = prompt_builder.build_prompt(
            query=parsed.query,
            diff_results=diff_results
        )

        # Initialize LLM client based on provider
        llm_client = None
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
            raise CLIError(f"Unsupported LLM provider: {config.llm.provider}")

        # Call LLM
        import time
        start_time = time.time()
        try:
            llm_response = llm_client.complete(
                messages=prompt_result.to_messages(),
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens
            )
            llm_latency_ms = (time.time() - start_time) * 1000

            # T16: Log the request
            logger.log_request(
                repo_root=str(repo_root),
                query=parsed.query,
                index_valid=is_valid,
                index_rebuilt=needs_rebuild,
                candidate_count=retrieval_engine.get_stats().candidate_count if retrieval_engine.get_stats() else 0,
                top_k_count=len(results),
                context_tokens=prompt_result.context_tokens,
                llm_model=config.llm.model,
                llm_latency_ms=llm_latency_ms,
                response_status="success",
                files_specified=parsed.files,
                branch_specified=parsed.branch,
                referenced_commits=prompt_result.referenced_commits
            )

            # T17: Output results
            print("\n" + "="*80)
            print("GIMI RESPONSE")
            print("="*80)
            print(llm_response.content)
            print("="*80)

            # Show referenced commits
            if prompt_result.referenced_commits:
                print("\nReferenced Commits:")
                for i, commit_hash in enumerate(prompt_result.referenced_commits[:10], 1):
                    # Find the commit in results to get the message
                    for result in results:
                        if result.commit.hash == commit_hash:
                            print(f"  {i}. {commit_hash[:7]}: {result.commit.message[:60]}...")
                            break

            return 0

        except LLMError as e:
            llm_latency_ms = (time.time() - start_time) * 1000
            logger.log_request(
                repo_root=str(repo_root),
                query=parsed.query,
                index_valid=is_valid,
                index_rebuilt=needs_rebuild,
                candidate_count=0,
                top_k_count=0,
                context_tokens=0,
                llm_model=config.llm.model,
                llm_latency_ms=llm_latency_ms,
                response_status="llm_error",
                error_message=str(e),
                files_specified=parsed.files,
                branch_specified=parsed.branch
            )
            raise CLIError(f"LLM error: {e}")

        return 0

    except CLIError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except RepoError as e:
        print(f"Repository Error: {e}", file=sys.stderr)
        return 1
    except LockError as e:
        print(f"Lock Error: {e}", file=sys.stderr)
        return 1
    except ConfigError as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
