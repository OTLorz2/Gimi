"""T14: Prompt assembly and LLM call."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

from .lightweight_index import get_commit_meta


def build_prompt(
    query: str,
    commit_diffs: List[Tuple[str, str]],
    conn_light,
) -> str:
    """
    Build user message: user query + formatted reference commits with diffs.
    Each block: commit hash, message (from index), then diff.
    """
    blocks = [f"User request: {query}\n"]
    blocks.append("Reference git history (commit and diff):\n")
    for commit_hash, diff_text in commit_diffs:
        meta = get_commit_meta(conn_light, commit_hash) if conn_light else None
        msg = meta.message if meta else "(no message)"
        blocks.append(f"--- Commit: {commit_hash} ---")
        blocks.append(f"Message: {msg}")
        blocks.append(diff_text or "(no diff)")
        blocks.append("")
    blocks.append("Based on the above git history and the user request, provide concise suggestions (code or explanation). Mention which commit(s) you reference.")
    return "\n".join(blocks)


def call_llm(
    prompt: str,
    model: str = "gpt-4o-mini",
    api_key: Optional[str] = None,
) -> str:
    """
    Call LLM with the assembled prompt; return response text.
    Uses OpenAI API; key from arg or GIMI_API_KEY env.
    """
    api_key = api_key or os.environ.get("GIMI_API_KEY")
    if not api_key:
        return "(Set GIMI_API_KEY to get LLM suggestions. No API key provided.)"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a programming assistant. Use the provided git history to suggest code changes or explain past fixes. Be concise and cite commit hashes when relevant."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:
        return f"(LLM call failed: {e})"
