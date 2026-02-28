"""
T3: CLI entry and argument parsing.

This module handles:
- CLI argument parsing for the gimi command
- Subcommand support (index, search, etc.)
- Input validation
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .repo import RepoError, NotAGitRepoError, setup_gimi
from .lock import LockAcquisitionError, LockHeldByOtherProcess


class GimiCLI:
    """
    Main CLI entry point for the gimi auxiliary programming agent.
    """

    def __init__(self):
        self.parser = self._create_parser()

    def _create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser with all subcommands."""
        parser = argparse.ArgumentParser(
            prog='gimi',
            description='Gimi - Auxiliary programming agent for git repositories',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  gimi index                              # Build/update the commit index
  gimi search "optimize memory usage"     # Search for relevant commits
  gimi ask "Why was this function added?" # Ask about code history
  gimi ask "How do I fix this bug?" --file src/main.py
            """
        )

        subparsers = parser.add_subparsers(dest='command', help='Available commands')

        # index command
        index_parser = subparsers.add_parser(
            'index',
            help='Build or update the commit index',
            description='Traverse git history and build the lightweight and vector indices.'
        )
        index_parser.add_argument(
            '--full',
            action='store_true',
            help='Force full rebuild (ignore existing index)'
        )
        index_parser.add_argument(
            '--incremental',
            action='store_true',
            help='Only index new commits since last update'
        )
        index_parser.add_argument(
            '--branch',
            '-b',
            action='append',
            dest='branches',
            help='Branch to index (can be specified multiple times, default: all branches)'
        )

        # search command
        search_parser = subparsers.add_parser(
            'search',
            help='Search commits by keywords, path, or semantic similarity',
            description='Search the commit index using various retrieval strategies.'
        )
        search_parser.add_argument(
            'query',
            help='Search query (keywords or natural language)'
        )
        search_parser.add_argument(
            '--file',
            '-f',
            action='append',
            dest='files',
            help='Filter by file path (can be specified multiple times)'
        )
        search_parser.add_argument(
            '--branch',
            '-b',
            help='Filter by branch'
        )
        search_parser.add_argument(
            '--semantic',
            '-s',
            action='store_true',
            help='Use semantic search (vector similarity)'
        )
        search_parser.add_argument(
            '--top-k',
            '-k',
            type=int,
            default=10,
            help='Number of results to return (default: 10)'
        )
        search_parser.add_argument(
            '--no-semantic',
            action='store_true',
            help='Disable semantic search, use only keyword/path matching'
        )

        # ask command
        ask_parser = subparsers.add_parser(
            'ask',
            help='Ask a question about the codebase history',
            description='Retrieve relevant commits and ask LLM for insights or suggestions.'
        )
        ask_parser.add_argument(
            'question',
            help='Your question or request (e.g., "Why was this changed?", "How do I fix this?")'
        )
        ask_parser.add_argument(
            '--file',
            '-f',
            action='append',
            dest='files',
            help='Focus on specific files (can be specified multiple times)'
        )
        ask_parser.add_argument(
            '--branch',
            '-b',
            help='Focus on specific branch'
        )
        ask_parser.add_argument(
            '--top-k',
            '-k',
            type=int,
            default=5,
            help='Number of commits to use as context (default: 5)'
        )
        ask_parser.add_argument(
            '--model',
            '-m',
            help='LLM model to use (overrides config)'
        )
        ask_parser.add_argument(
            '--no-stream',
            action='store_true',
            help='Disable streaming output, wait for complete response'
        )

        # Global options
        parser.add_argument(
            '--config',
            '-c',
            help='Path to config file (default: .gimi/config.json)'
        )
        parser.add_argument(
            '--verbose',
            '-v',
            action='count',
            default=0,
            help='Increase verbosity (use -v, -vv, or -vvv)'
        )
        parser.add_argument(
            '--quiet',
            '-q',
            action='store_true',
            help='Suppress non-error output'
        )
        parser.add_argument(
            '--version',
            action='version',
            version='%(prog)s 0.1.0'
        )

        return parser

    def parse_args(self, args: Optional[Sequence[str]] = None) -> argparse.Namespace:
        """Parse command line arguments."""
        return self.parser.parse_args(args)

    def run(self, args: Optional[Sequence[str]] = None) -> int:
        """
        Main entry point for the CLI.

        Args:
            args: Command line arguments (defaults to sys.argv[1:])

        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        parsed = self.parse_args(args)

        # Handle no command
        if parsed.command is None:
            self.parser.print_help()
            return 0

        try:
            # Setup repository and .gimi directory
            repo_root, gimi_paths = setup_gimi()

            if parsed.verbose >= 2:
                print(f"Repository root: {repo_root}")
                print(f".gimi directory: {gimi_paths.gimi_dir}")

            # Dispatch to command handlers
            if parsed.command == 'index':
                return self._handle_index(parsed, repo_root, gimi_paths)
            elif parsed.command == 'search':
                return self._handle_search(parsed, repo_root, gimi_paths)
            elif parsed.command == 'ask':
                return self._handle_ask(parsed, repo_root, gimi_paths)
            else:
                print(f"Unknown command: {parsed.command}", file=sys.stderr)
                return 1

        except NotAGitRepoError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        except RepoError as e:
            print(f"Repository error: {e}", file=sys.stderr)
            return 1
        except LockHeldByOtherProcess as e:
            print(f"Lock error: {e}", file=sys.stderr)
            print("Another gimi process is currently running.", file=sys.stderr)
            return 1
        except LockAcquisitionError as e:
            print(f"Failed to acquire lock: {e}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            return 130

    def _handle_index(self, args: argparse.Namespace, repo_root: Path, gimi_paths) -> int:
        """Handle the 'index' command."""
        if not args.quiet:
            print("Indexing commits...")
            if args.full:
                print("  Mode: Full rebuild")
            elif args.incremental:
                print("  Mode: Incremental update")
            if args.branches:
                print(f"  Branches: {', '.join(args.branches)}")

        # TODO: Implement actual indexing in T6-T9
        if args.verbose:
            print("(Index command handler placeholder - T6-T9)")

        if not args.quiet:
            print("Indexing complete (placeholder).")
        return 0

    def _handle_search(self, args: argparse.Namespace, repo_root: Path, gimi_paths) -> int:
        """Handle the 'search' command."""
        if args.verbose:
            print(f"Searching for: {args.query}")
            if args.files:
                print(f"  Files: {args.files}")
            if args.branch:
                print(f"  Branch: {args.branch}")
            print(f"  Top-K: {args.top_k}")

        # TODO: Implement actual search in T10-T12
        if args.verbose:
            print("(Search command handler placeholder - T10-T12)")

        print(f"Search results for: {args.query}")
        print("(Placeholder - no results yet)")
        return 0

    def _handle_ask(self, args: argparse.Namespace, repo_root: Path, gimi_paths) -> int:
        """Handle the 'ask' command."""
        if args.verbose:
            print(f"Question: {args.question}")
            if args.files:
                print(f"  Files: {args.files}")
            if args.branch:
                print(f"  Branch: {args.branch}")
            print(f"  Top-K: {args.top_k}")

        # TODO: Implement actual ask flow in T13-T15
        if args.verbose:
            print("(Ask command handler placeholder - T13-T15)")

        print(f"Answer to: {args.question}")
        print("(Placeholder - no answer yet)")
        return 0


def main(args: Optional[Sequence[str]] = None) -> int:
    """
    Main entry point for the gimi CLI.

    Args:
        args: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code
    """
    cli = GimiCLI()
    return cli.run(args)


if __name__ == '__main__':
    sys.exit(main())
