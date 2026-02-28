# Gimi

An auxiliary programming agent for git repositories that helps you understand code history and provides intelligent suggestions based on commit history.

## Features

- Hybrid retrieval (keyword + path + semantic) to find relevant commits
- Intelligent diff context assembly for LLM
- Support for large repositories with checkpoint/resume
- File-based locking for safe concurrent operations

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Basic usage
gimi "How do I implement feature X?"

# Focus on specific files
gimi "Why is this function slow?" --file src/main.py --file src/utils.py

# Search specific branch
gimi "What changed in the API?" --branch main

# Force rebuild index
gimi "Question" --rebuild-index
```

## Project Structure

```
.gimi/                  # Created in repository root
├── config.json         # Configuration
├── index/              # Lightweight index (commit metadata)
├── vectors/            # Vector index for semantic search
├── cache/              # Diff cache
└── logs/               # Operation logs
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black gimi/

# Type check
mypy gimi/
```

## License

MIT License
