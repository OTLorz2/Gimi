"""T17: Centralized error handling and user-facing messages."""

from __future__ import annotations

import click


class GimiError(Exception):
    """Base for user-facing errors with a clear message."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def handle_error(e: BaseException) -> str:
    """Map known exceptions to a short user message."""
    if isinstance(e, GimiError):
        return e.message
    if isinstance(e, RuntimeError):
        s = str(e)
        if "Not inside a git repository" in s or "git" in s.lower():
            return "Not inside a git repository. Run gimi from a path where git records can be queried."
        if "Another gimi process" in s or "lock" in s.lower():
            return "Another gimi process is writing to this repository's index. Wait for it to finish or kill that process."
    if isinstance(e, PermissionError):
        return "Permission denied when writing to .gimi. Check directory permissions."
    return f"Error: {e}"


def report_and_exit(e: BaseException, exit_code: int = 1) -> None:
    """Echo error message and exit."""
    click.echo(handle_error(e), err=True)
    raise SystemExit(exit_code)
