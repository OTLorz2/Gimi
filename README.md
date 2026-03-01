# Gimi

CLI agent that uses git history to suggest code changes. Run from inside a git repository; all generated data is stored under `.gimi/` at the repo root.

## Requirements

- Python 3.10+
- Git (must be run from a path where `git` can see the repo, e.g. repo root or any subdirectory)
- Optional: `GIMI_API_KEY` for OpenAI (embeddings and LLM). Without it, suggestions use only keyword/path retrieval and a placeholder message.

## Install

```bash
cd Gimi
pip install -e ".[embedding,llm]"
```

Or minimal (no OpenAI):

```bash
pip install -e .
```

## Usage

```bash
# From anywhere inside the repo
gimi "fix login timeout"
gimi --file src/auth/login.ts "why does this error?"
gimi --branch main "last time we changed this logic"
```

- **First run**: Builds index (git walk + lightweight index + vectors) and writes to `<repo_root>/.gimi/`. This may take a while on large repos.
- **Later runs**: Reuses index if refs match; otherwise prompts to rebuild or runs incremental update.

## Configuration

Non-sensitive options live in `.gimi/config.json` (created with defaults on first run). Example:

- `model` – LLM model (e.g. `gpt-4o-mini`)
- `top_k` – number of commits to send to the LLM (default 20)
- `candidate_size` – candidate set size before semantic ranking (default 80)
- `max_commits_indexed` – cap on commits to index (default 2000)
- `max_diff_lines_per_file` / `max_files_per_commit` – truncation for diffs
- `branches` – `null` for all branches, or a list e.g. `["main"]`
- `enable_rerank` – optional second-stage rerank (default false)

**API key**: Set `GIMI_API_KEY` in the environment. Do not put it in `config.json`.

## Directory layout (`.gimi/`)

- `config.json` – config
- `refs_snapshot.json` – git refs at last index build (for validity check)
- `index/` – lightweight index (SQLite)
- `vectors/` – vector index for semantic search
- `cache/` – optional diff cache
- `logs/` – request and error logs

## Errors

- **Not inside a git repository** – Run from a directory that is inside a git repo (same as running `git status`).
- **Another gimi process is writing** – Only one process can build/update the index at a time; wait or kill the other process.
- **Index stale** – Refs changed since last index; rebuild will be triggered or suggested.
