"""T8: Vector index - embed message + paths per commit, store and query by similarity."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

from .git_walk import CommitMeta


VECTORS_DB = "vectors.db"
EMBEDDING_DIM = 1536  # OpenAI text-embedding-3-small


def _text_for_embedding(meta: CommitMeta) -> str:
    """Build single string for embedding: message + path list."""
    return meta.message + " " + " ".join(meta.paths)


def get_embedding(text: str, api_key: Optional[str] = None) -> List[float]:
    """
    Return embedding vector for text. Uses OpenAI if API key set else deterministic fallback.
    """
    api_key = api_key or os.environ.get("GIMI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            r = client.embeddings.create(model="text-embedding-3-small", input=text[:8000])
            return r.data[0].embedding
        except Exception:
            pass
    # Fallback: deterministic pseudo-embedding (hash-based) so retrieval is stable without API
    import hashlib
    vec = []
    h = text.encode()
    while len(vec) < EMBEDDING_DIM:
        h = hashlib.sha256(h).digest()
        vec.extend((b - 128) / 128.0 for b in h)
    return vec[:EMBEDDING_DIM]


def _cosine_sim(a: List[float], b: List[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (na * nb)


def _init_vectors_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vectors (
            hash TEXT PRIMARY KEY,
            embedding_json TEXT NOT NULL
        )
    """)
    conn.commit()


def open_vectors(gimi_dir: Path) -> sqlite3.Connection:
    """Open or create vectors DB."""
    vec_dir = gimi_dir / "vectors"
    vec_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(vec_dir / VECTORS_DB))
    _init_vectors_db(conn)
    return conn


def write_embedding(conn: sqlite3.Connection, commit_hash: str, embedding: List[float]) -> None:
    """Store one commit's embedding."""
    conn.execute(
        "INSERT OR REPLACE INTO vectors (hash, embedding_json) VALUES (?, ?)",
        (commit_hash, json.dumps(embedding)),
    )
    conn.commit()


def get_embedding_by_hash(conn: sqlite3.Connection, commit_hash: str) -> Optional[List[float]]:
    """Load embedding for a commit."""
    cur = conn.execute("SELECT embedding_json FROM vectors WHERE hash = ?", (commit_hash,))
    row = cur.fetchone()
    if not row:
        return None
    return json.loads(row[0])


def search_similar(
    conn: sqlite3.Connection,
    query_embedding: List[float],
    candidate_hashes: List[str],
    top_k: int,
) -> List[Tuple[str, float]]:
    """
    From candidate_hashes, return top_k (hash, score) by cosine similarity to query_embedding.
    """
    rows = []
    for h in candidate_hashes:
        emb = get_embedding_by_hash(conn, h)
        if emb is None:
            continue
        score = _cosine_sim(query_embedding, emb)
        rows.append((h, score))
    rows.sort(key=lambda x: -x[1])
    return rows[:top_k]
