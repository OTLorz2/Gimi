"""Configuration management for Gimi."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any


class ConfigError(Exception):
    """Raised when configuration operations fail."""
    pass


@dataclass
class RetrievalConfig:
    """Configuration for retrieval parameters."""
    keyword_candidates: int = 100  # Initial candidates from keyword/path search
    top_k: int = 20  # Final top-K commits after semantic retrieval
    rerank_top_k: int = 10  # After optional reranking
    enable_rerank: bool = False  # Enable two-stage reranking


@dataclass
class ContextConfig:
    """Configuration for context assembly."""
    max_files_per_commit: int = 10  # Maximum files to include per commit
    max_lines_per_file: int = 50  # Maximum lines per file in diff
    max_total_tokens: int = 4000  # Estimated token limit for context
    enable_cache: bool = True  # Enable diff caching


@dataclass
class LLMConfig:
    """Configuration for LLM API."""
    provider: str = "openai"  # openai, anthropic, etc.
    model: str = "gpt-4o-mini"  # Model name
    api_key: Optional[str] = None  # API key (can also use env var)
    api_base: Optional[str] = None  # Custom API base URL
    max_tokens: int = 2000  # Maximum tokens in response
    temperature: float = 0.3  # Sampling temperature
    timeout: float = 60.0  # Request timeout in seconds


@dataclass
class IndexConfig:
    """Configuration for index building."""
    max_commits: Optional[int] = None  # Max commits to index (None = unlimited)
    max_age_days: Optional[int] = None  # Only index commits within N days
    branches: List[str] = field(default_factory=lambda: ["main", "master"])  # Branches to index
    include_all_branches: bool = False  # Index all branches
    batch_size: int = 100  # Commits to process per batch (for checkpointing)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"  # For semantic search
    embedding_dim: int = 384  # Dimension of embeddings


@dataclass
class GimiConfig:
    """Main configuration class for Gimi."""
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    index: IndexConfig = field(default_factory=IndexConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GimiConfig":
        """Create config from dictionary."""
        retrieval = RetrievalConfig(**data.get("retrieval", {}))
        context = ContextConfig(**data.get("context", {}))
        llm = LLMConfig(**data.get("llm", {}))
        index = IndexConfig(**data.get("index", {}))

        return cls(
            retrieval=retrieval,
            context=context,
            llm=llm,
            index=index
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "retrieval": asdict(self.retrieval),
            "context": asdict(self.context),
            "llm": asdict(self.llm),
            "index": asdict(self.index)
        }


def get_config_path(gimi_dir: Path) -> Path:
    """Get path to config file."""
    return gimi_dir / "config.json"


def load_config(gimi_dir: Path, custom_path: Optional[Path] = None) -> GimiConfig:
    """
    Load configuration from file.

    Args:
        gimi_dir: Path to .gimi directory
        custom_path: Optional custom config file path

    Returns:
        Loaded configuration

    Raises:
        ConfigError: If config file is invalid
    """
    config_path = custom_path or get_config_path(gimi_dir)

    if not config_path.exists():
        # Return default config
        return GimiConfig()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return GimiConfig.from_dict(data)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config file: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to load config: {e}")


def save_config(config: GimiConfig, gimi_dir: Path, custom_path: Optional[Path] = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save
        gimi_dir: Path to .gimi directory
        custom_path: Optional custom config file path

    Raises:
        ConfigError: If config cannot be saved
    """
    config_path = custom_path or get_config_path(gimi_dir)

    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Don't save sensitive data (API key) to file if it comes from env
        data = config.to_dict()

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise ConfigError(f"Failed to save config: {e}")


def init_config(gimi_dir: Path) -> GimiConfig:
    """
    Initialize default configuration if it doesn't exist.

    Args:
        gimi_dir: Path to .gimi directory

    Returns:
        Configuration (loaded or default)
    """
    config_path = get_config_path(gimi_dir)

    if config_path.exists():
        return load_config(gimi_dir)

    # Create default config
    config = GimiConfig()

    # Try to get API key from environment
    if os.environ.get("OPENAI_API_KEY"):
        config.llm.api_key = os.environ.get("OPENAI_API_KEY")

    # Save default config
    save_config(config, gimi_dir)

    return config
