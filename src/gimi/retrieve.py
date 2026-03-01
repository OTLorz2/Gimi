"""T10/T11/T12: Keyword+path retrieval, semantic fusion, optional rerank."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from .config import load_config
from .lightweight_index import open_index, search_by_keywords, search_by_path
from .vector_index import get_embedding, open_vectors, search_similar


def get_candidates(
    conn_light: sqlite3.Connection,
    query: str,
    file_path: Optional[str],
    candidate_size: int,
    branch: Optional[str] = None,
) -> List[str]:
    """
    T10: Keyword + path retrieval. Returns candidate commit hashes (up to candidate_size).
    Merges results from keyword search and path filter; deduplicates and caps size.
    """
    by_keyword = search_by_keywords(conn_light, query, limit=candidate_size)
    if file_path:
        by_path = search_by_path(conn_light, file_path, limit=candidate_size)
        # Merge: prefer path hits, then keyword hits, dedupe
        seen = set()
        merged = []
        for h in by_path:
            if h not in seen:
                seen.add(h)
                merged.append(h)
        for h in by_keyword:
            if h not in seen:
                seen.add(h)
                merged.append(h)
            if len(merged) >= candidate_size:
                break
        return merged[:candidate_size]
    return by_keyword[:candidate_size]


def fuse_and_rank(
    conn_light: sqlite3.Connection,
    conn_vec: sqlite3.Connection,
    query: str,
    candidate_hashes: List[str],
    top_k: int,
    api_key: Optional[str] = None,
) -> List[Tuple[str, float]]:
    """
    T11: Semantic ranking on candidates. Embed query, then similarity sort over candidates; return top_k (hash, score).
    """
    if not candidate_hashes:
        return []
    import os
    query_emb = get_embedding(query, api_key=api_key or os.environ.get("GIMI_API_KEY"))
    return search_similar(conn_vec, query_emb, candidate_hashes, top_k)


def rerank(
    ranked: List[Tuple[str, float]],
    query: str,
    top_n: int,
    conn_light: Optional[sqlite3.Connection] = None,
) -> List[Tuple[str, float]]:
    """
    T12: Optional second-stage rerank. For now we just take top_n by existing score (no cross-encoder).
    When enable_rerank and cross-encoder/LLM scoring are added, this is the hook.
    """
    return ranked[:top_n]
