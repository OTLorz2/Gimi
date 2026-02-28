# Gimi - Git Repository Assistant

Gimi is an AI-powered CLI tool that helps developers understand their git repositories by analyzing commit history and providing intelligent suggestions.

## Features

- **Semantic Search**: Find relevant commits using natural language queries
- **Hybrid Retrieval**: Combines keyword, path, and semantic search for best results
- **Contextual Understanding**: Analyzes commit diffs to provide relevant suggestions
- **LLM Integration**: Supports OpenAI and Anthropic models
- **Efficient Indexing**: SQLite-based indexing with checkpoint/resume support

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd Gimi-v1

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

## Configuration

Gimi stores its configuration in `.gimi/config.json` within your repository. The first time you run Gimi, it will create a default configuration.

### Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key
- `ANTHROPIC_API_KEY`: Your Anthropic API key

### Configuration Options

```json
{
  "retrieval": {
    "keyword_candidates": 100,
    "top_k": 20,
    "rerank_top_k": 10,
    "enable_rerank": false
  },
  "context": {
    "max_files_per_commit": 10,
    "max_lines_per_file": 50,
    "max_total_tokens": 4000
  },
  "llm": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.3,
    "max_tokens": 2000
  },
  "index": {
    "max_commits": null,
    "max_age_days": null,
    "branches": ["main", "master"],
    "batch_size": 100,
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
  }
}
```

## Usage

### Basic Usage

```bash
# Ask a question about your repository
gimi "How do I implement user authentication?"

# Focus on specific files
gimi "What changed in the API?" --file src/api.py --file src/routes.py

# Search specific branch
gimi "Find the bug fix for the login issue" --branch main
```

### Index Management

```bash
# Force rebuild the index
gimi "Your query" --rebuild-index

# The index is automatically updated when commits change
```

### Advanced Options

```bash
# Use custom config file
gimi "Your query" --config /path/to/config.json

# Show version
gimi --version
```

## Directory Structure

When you run Gimi in a repository, it creates a `.gimi/` directory:

```
.gimi/
├── config.json          # Configuration file
├── index/
│   └── commits.db       # SQLite database with commit metadata
├── vectors/
│   └── vectors.db       # Vector embeddings for semantic search
├── cache/
│   └── ...              # Cached commit diffs
├── logs/
│   ├── requests.jsonl   # Request logs
│   ├── index_builds.jsonl  # Index build logs
│   └── errors.log       # Error logs
└── refs_snapshot.json   # Git refs snapshot for index validity
```

## Development

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=gimi

# Run specific test file
python -m pytest tests/test_repo.py
```

### Code Style

```bash
# Format with black
black gimi/

# Check with flake8
flake8 gimi/

# Type check with mypy
mypy gimi/
```

## Architecture

Gimi consists of several key components:

1. **Repository Management** (`gimi/core/repo.py`): Handles git repository discovery and `.gimi` directory setup.

2. **Indexing** (`gimi/index/`):
   - `lightweight.py`: SQLite-based metadata index
   - `vector_index.py`: Vector embeddings for semantic search
   - `embeddings.py`: Embedding providers (sentence-transformers, OpenAI)
   - `builder.py`: Index construction with checkpoint/resume

3. **Retrieval** (`gimi/retrieval/engine.py`): Hybrid search combining keyword, path, and semantic retrieval.

4. **Context Assembly** (`gimi/context/diff_manager.py`): Fetches and truncates commit diffs.

5. **LLM Integration** (`gimi/llm/`): Client implementations for OpenAI and Anthropic APIs.

6. **Observability** (`gimi/core/logging.py`): Structured logging for requests, index builds, and errors.

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Troubleshooting

### Common Issues

**Q: Gimi says "Not a git repository"**
A: Make sure you're running Gimi inside a git repository. Run `git status` to verify.

**Q: Index build fails with "sentence-transformers not installed"**
A: Install sentence-transformers: `pip install sentence-transformers`

**Q: OpenAI API errors**
A: Make sure your `OPENAI_API_KEY` environment variable is set correctly.

**Q: Index is out of date**
A: Run with `--rebuild-index` to force a full rebuild.

## Support

For issues and feature requests, please use the GitHub issue tracker.
