"""CLI entry point and argument parsing for Gimi."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from gimi.core.repo import find_repo_root, ensure_gimi_structure, RepoError
from gimi.core.lock import LockError


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

        # TODO: T4+ - Configuration loading and refs snapshot
        # TODO: T5+ - Index validity verification
        # TODO: T6+ - Git traversal and commit metadata
        # ... more tasks to come

        # Placeholder output for phase 1 completion
        print(f"Repository root: {repo_root}")
        print(f"Gimi directory: {gimi_dir}")
        print(f"Query: {parsed.query or '(none)'}")
        if parsed.files:
            print(f"Files: {', '.join(parsed.files)}")
        if parsed.branch:
            print(f"Branch: {parsed.branch}")

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
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
