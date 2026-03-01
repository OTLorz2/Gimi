"""CLI entry and full pipeline."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import click

from .config import load_config
from .diff_fetch import fetch_diffs_for_commits
from .env import ensure_gimi_dirs, get_gimi_dir, get_repo_root
from .errors import report_and_exit
from .index_build import build_index
from .index_validity import check_index_validity
from .lightweight_index import open_index
from .llm import build_prompt, call_llm
from .logs import init_request_log, log_request_end
from .output import print_suggestion
from .retrieve import fuse_and_rank, get_candidates, rerank
from .vector_index import open_vectors


@click.command()
@click.argument("query", required=False)
@click.option("--file", "file_path", type=click.Path(path_type=Path), default=None, help="Relevant file path for path-based filtering.")
@click.option("--branch", default=None, help="Limit to this branch (e.g. main).")
@click.option("--index", "index_only", is_flag=True, help="Only build/update index, then exit.")
@click.option("--force", is_flag=True, help="With --index: force full index rebuild.")
def cli(
    query: Optional[str],
    file_path: Optional[Path],
    branch: Optional[str],
    index_only: bool,
    force: bool,
) -> None:
    """Gimi: suggest changes using git history. Run from inside a git repository."""
    try:
        repo_root = get_repo_root()
    except RuntimeError as e:
        report_and_exit(e)
    ensure_gimi_dirs(repo_root)
    gimi_dir = get_gimi_dir(repo_root)
    if index_only:
        click.echo("Building index...")
        try:
            build_index(repo_root, gimi_dir, force_full=force, api_key=os.environ.get("GIMI_API_KEY"))
        except RuntimeError as e:
            report_and_exit(e)
        click.echo("Index built.")
        return
    if not query:
        click.echo("Usage: gimi QUERY  or  gimi --index", err=True)
        raise SystemExit(1)
    _run_ask(repo_root, gimi_dir, query, file_path, branch)


def _run_ask(
    repo_root: Path,
    gimi_dir: Path,
    query: str,
    file_path: Optional[Path],
    branch: Optional[str],
) -> None:
    config = load_config(gimi_dir)
    index_usable, need_rebuild = check_index_validity(repo_root, gimi_dir)
    if need_rebuild or not index_usable:
        click.echo("Index missing or stale. Building index...")
        try:
            build_index(repo_root, gimi_dir, force_full=need_rebuild, api_key=os.environ.get("GIMI_API_KEY"))
        except RuntimeError as e:
            report_and_exit(e)
    request_id = init_request_log(gimi_dir, repo_root, index_reused=index_usable and not need_rebuild)
    candidate_size = config.get("candidate_size") or 80
    top_k = config.get("top_k") or 20
    file_path_str = str(file_path) if file_path else None
    conn_light = open_index(gimi_dir)
    conn_vec = open_vectors(gimi_dir)
    try:
        candidates = get_candidates(conn_light, query, file_path_str, candidate_size, branch)
        ranked = fuse_and_rank(conn_light, conn_vec, query, candidates, top_k, api_key=os.environ.get("GIMI_API_KEY"))
        if config.get("enable_rerank"):
            rerank_top = config.get("rerank_top") or 8
            ranked = rerank(ranked, query, rerank_top, conn_light)
        top_hashes = [h for h, _ in ranked]
        commit_diffs = fetch_diffs_for_commits(
            repo_root,
            top_hashes,
            max_diff_lines_per_file=config.get("max_diff_lines_per_file") or 80,
            max_files_per_commit=config.get("max_files_per_commit") or 10,
        )
        context_chars = sum(len(d) for _, d in commit_diffs)
        prompt = build_prompt(query, commit_diffs, conn_light)
        t0 = time.perf_counter()
        suggestion = call_llm(
            prompt,
            model=config.get("model") or "gpt-4o-mini",
            api_key=os.environ.get("GIMI_API_KEY"),
        )
        llm_elapsed = time.perf_counter() - t0
        log_request_end(gimi_dir, request_id, len(candidates), len(top_hashes), context_chars, llm_elapsed)
        print_suggestion(suggestion, top_hashes, conn_light)
    except Exception as e:
        report_and_exit(e)
    finally:
        conn_light.close()
        conn_vec.close()


def main() -> None:
    """Entry point for console script."""
    cli()


def run() -> None:
    main()


if __name__ == "__main__":
    run()
