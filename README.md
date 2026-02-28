# Gimi - AI-Powered Git Assistant

Gimi is an intelligent CLI tool that analyzes your git history to provide AI-powered code suggestions, explanations, and insights. By combining hybrid retrieval (keyword + path + semantic) with Large Language Models, Gimi helps you understand your codebase better and write better code.

## Features

- **Hybrid Retrieval**: Combines BM25 keyword search, path matching, and semantic vector search using Reciprocal Rank Fusion (RRF)
- **AI-Powered Suggestions**: Integrates with OpenAI, Anthropic, and other LLM providers
- **Smart Indexing**: Incremental indexing with resume capability for large repositories
- **File-Aware Analysis**: Focus analysis on specific files or directories
- **Configurable**: Extensive configuration options for retrieval, context, and LLM settings

## Installation

### Prerequisites

- Python 3.8 or higher
- Git repository (Gimi must be run inside a git repository)

### Install from Source

```bash
# Clone the repository
git clone <repository-url>
cd gimi

# Install in development mode
pip install -e .

# Or install with specific embedding dependencies
pip install -e ".[embeddings]"
```

### Dependencies

Core dependencies (installed automatically):
- numpy - Numerical computations
- requests - HTTP client for API calls

Optional dependencies:
- sentence-transformers - For local embeddings (recommended)
- openai - For OpenAI API integration
- anthropic - For Anthropic API integration

## Quick Start

1. **Navigate to your git repository**:
```bash
cd /path/to/your/repo
```

2. **Run Gimi with a question**:
```bash
gimi "How do I implement error handling in this module?"
```

3. **Focus on specific files**:
```bash
gimi "Explain the authentication flow" --file src/auth.py
```

4. **Analyze a specific branch**:
```bash
gimi "What changed in the API recently?" --branch main
```

## Configuration

Gimi stores configuration in `.gimi/config.json` in your repository root. The configuration is created automatically on first run with sensible defaults.

### Configuration File Structure

```json
{
  "llm": {
    "provider": "openai",
    "api_key": "your-api-key",
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 2048,
    "timeout": 60
  },
  "retrieval": {
    "top_k": 10,
    "rrf_k": 60.0,
    "keyword_weight": 1.0,
    "path_weight": 1.0,
    "vector_weight": 1.5,
    "normalize_scores": true,
    "enable_reranking": false
  },
  "context": {
    "max_files_per_commit": 5,
    "max_lines_per_file": 100,
    "max_total_tokens": 4000
  },
  "index": {
    "embedding_provider": "local",
    "embedding_model": "all-MiniLM-L6-v2",
    "embedding_dimension": 384,
    "batch_size": 32,
    "max_commits": 10000
  }
}
```

### Environment Variables

You can also configure Gimi using environment variables:

- `GIMI_API_KEY` - API key for LLM provider
- `GIMI_PROVIDER` - LLM provider (openai, anthropic)
- `GIMI_MODEL` - Model name
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key

Environment variables override configuration file settings.

## How It Works

### Architecture Overview

```
User Query
    |
    v
[CLI] -> [Repo Discovery] -> [.gimi Directory]
    |
    v
[Index Check] -> [Build/Update Index] (if needed)
    |
    v
[Hybrid Retrieval]
    |-- [Keyword Search (BM25)]
    |-- [Path Search]
    |-- [Vector Search]
    |
    v
[RRF Fusion]
    |
    v
[Diff Retrieval]
    |
    v
[Prompt Assembly]
    |
    v
[LLM Call]
    |
    v
[Response Display]
```

### Retrieval Process

1. **Keyword Search**: Uses BM25 algorithm to score commits based on term frequency in commit messages
2. **Path Search**: Matches commits that modified files matching the specified paths
3. **Vector Search**: Uses semantic embeddings to find commits with similar meaning

The results from all three sources are combined using **Reciprocal Rank Fusion (RRF)**, which effectively combines rankings without requiring score normalization.

### Indexing

Gimi maintains several indexes in `.gimi/`:

- **index/**: Lightweight index storing commit metadata (hash, message, files, timestamp)
- **vectors/**: Vector embeddings for semantic search
- **cache/**: Cached diffs to avoid repeated `git show` calls
- **logs/**: Operation logs for debugging

The index is incrementally updated when the repository changes (detected via refs snapshot).

## Advanced Usage

### Custom Configuration

Create a `.gimi/config.json` with custom settings:

```json
{
  "llm": {
    "provider": "anthropic",
    "model": "claude-3-opus-20240229",
    "temperature": 0.5
  },
  "retrieval": {
    "top_k": 15,
    "vector_weight": 2.0
  }
}
```

### Working with Large Repositories

For large repositories, you may want to limit the index size:

```bash
# Set max commits in config.json
{
  "index": {
    "max_commits": 5000
  }
}
```

### Force Rebuild Index

If you suspect index corruption or want a fresh start:

```bash
gimi "Your query" --rebuild-index
```

### Verbose Mode

For debugging or understanding what's happening:

```bash
gimi "Your query" --verbose
```

This shows:
- Index building progress
- Retrieval statistics
- LLM call timing

## Troubleshooting

### Common Issues

#### "Not a git repository"

Make sure you're running Gimi from within a git repository:

```bash
git status  # Should show repo status
gimi "query"  # Now this should work
```

#### "Could not acquire lock"

Another Gimi process is running. Either wait for it to complete or remove the stale lock:

```bash
# Check if another process is running
ps aux | grep gimi

# If not, remove stale lock
rm .gimi/lock
```

#### "Failed to generate embeddings"

If using local embeddings, ensure sentence-transformers is installed:

```bash
pip install sentence-transformers
```

If using API embeddings, check your API key:

```bash
export OPENAI_API_KEY="your-key"
```

#### "Index is corrupted"

Rebuild the index:

```bash
gimi "query" --rebuild-index
```

### Getting Help

If you encounter issues not covered here:

1. Run with `--verbose` to get more details
2. Check `.gimi/logs/` for error logs
3. Ensure you're using the latest version

## Development

### Setting up Development Environment

```bash
# Clone the repository
git clone <repository-url>
cd gimi

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev,embeddings,openai,anthropic]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=gimi --cov-report=html

# Run specific test file
pytest tests/test_cli.py

# Run with verbose output
pytest -v
```

### Project Structure

```
gimi/
├── core/           # Core functionality
│   ├── cli.py      # CLI entry point
│   ├── config.py   # Configuration management
│   ├── exceptions.py # Custom exceptions
│   ├── git.py      # Git operations
│   ├── lock.py     # File locking
│   ├── logging.py  # Logging utilities
│   ├── refs.py     # Git refs management
│   └── repo.py     # Repository discovery
├── index/          # Indexing functionality
│   ├── builder.py  # Index builder
│   ├── embeddings.py # Embedding providers
│   ├── lightweight.py # Lightweight index
│   └── vector_index.py # Vector index
├── retrieval/      # Retrieval engine
│   └── engine.py   # Hybrid retrieval engine
├── context/        # Context management
│   └── diff_manager.py # Diff retrieval
├── llm/            # LLM integration
│   ├── client.py   # LLM clients
│   └── prompt_builder.py # Prompt construction
└── observability/  # Observability
    └── logging.py  # Request logging
```

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Sentence-Transformers for local embeddings
- OpenAI and Anthropic for LLM APIs
- The BM25 algorithm for efficient keyword retrieval
- Reciprocal Rank Fusion for effective result combination
