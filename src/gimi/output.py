"""T15: Output suggestion and reference commits to terminal."""

from __future__ import annotations

from typing import List, Optional, Tuple

import click

from .lightweight_index import get_commit_meta


def format_reference_commits(
    conn_light,
    commit_hashes: List[str],
) -> str:
    """Format a short list of reference commits (hash + message) for display."""
    if not conn_light or not commit_hashes:
        return ""
    lines = ["Reference commits:"]
    for h in commit_hashes[:15]:
        meta = get_commit_meta(conn_light, h)
        msg = (meta.message[:60] + "…") if meta and len(meta.message) > 60 else (meta.message if meta else "")
        lines.append(f"  {h[:8]}  {msg}")
    return "\n".join(lines)


def print_suggestion(
    suggestion: str,
    reference_hashes: List[str],
    conn_light=None,
) -> None:
    """Print LLM suggestion and reference commits to terminal (Click echo)."""
    click.echo("\n--- Suggestion ---\n")
    click.echo(suggestion)
    if reference_hashes:
        click.echo("")
        ref_block = format_reference_commits(conn_light, reference_hashes)
        if ref_block:
            click.echo(ref_block)
