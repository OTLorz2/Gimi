"""
Configuration loading and management (T4).

This module handles:
- Loading configuration from .gimi/config.json
- Saving configuration
- Providing default configuration values
- Configuration validation
"""
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union, List


class ConfigError(Exception):
    """Error related to configuration operations."""
    pass


@dataclass
class LLMConfig:
    """LLM configuration."""
    provider: str = "anthropic"
    model: str = "claude-opus-4-6"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 120
    max_context_tokens: int = 8000


@dataclass
class RetrievalConfig:
    """Retrieval configuration."""
    top_k: int = 20
    keyword_candidates: int = 100
    rerank_top_k: int = 10
    enable_rerank: bool = False
    keyword_weight: float = 0.3
    semantic_weight: float = 0.7
    path_weight: float = 0.0


@dataclass
class ContextConfig:
    """Context configuration."""
    max_files_per_commit: int = 10
    max_lines_per_file: int = 100
    max_total_commits: int = 5
    truncate_strategy: str = "head"
    max_diff_tokens: int = 4000
    max_total_tokens: int = 8000


@dataclass
class IndexConfig:
    """Index configuration."""
    max_commits: int = 1000
    branches: List[str] = field(default_factory=lambda: ["main", "master"])
    batch_size: int = 100
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_provider: str = "mock"
    embedding_cache_dir: Optional[str] = None


@dataclass
class ObservabilityConfig:
    """Observability configuration."""
    log_level: str = "INFO"
    enable_metrics: bool = True
    log_file: Optional[str] = None
    max_log_size_mb: int = 100


@dataclass
class GimiConfig:
    """Gimi complete configuration."""
    version: str = "0.1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    llm: LLMConfig = field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    index: IndexConfig = field(default_factory=IndexConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding sensitive info)."""
        data = asdict(self)
        # Ensure API key is not serialized
        if "llm" in data and "api_key" in data["llm"]:
            data["llm"]["api_key"] = None
        return data

    def save(self, config_path: Path) -> None:
        """Save configuration to file."""
        self.updated_at = datetime.now().isoformat()
        config_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def load(cls, config_path: Path) -> "GimiConfig":
        """Load configuration from file."""
        if not config_path.exists():
            return cls()

        data = json.loads(config_path.read_text(encoding="utf-8"))
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "GimiConfig":
        """Create configuration from dictionary."""
        config = cls(
            version=data.get("version", "0.1.0"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

        if "llm" in data:
            config.llm = LLMConfig(**data["llm"])
        if "retrieval" in data:
            config.retrieval = RetrievalConfig(**data["retrieval"])
        if "context" in data:
            config.context = ContextConfig(**data["context"])
        if "index" in data:
            config.index = IndexConfig(**data["index"])
        if "observability" in data:
            config.observability = ObservabilityConfig(**data["observability"])

        return config

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value by key path.

        Supports nested keys using dot notation (e.g., "llm.model").
        """
        keys = key_path.split('.')
        value = self

        for key in keys:
            if hasattr(value, key):
                value = getattr(value, key)
            else:
                return default

        return value

    def set(self, key_path: str, value: Any) -> None:
        """Set configuration value by key path."""
        keys = key_path.split('.')
        target = self

        for key in keys[:-1]:
            if not hasattr(target, key):
                setattr(target, key, {})
            target = getattr(target, key)

        setattr(target, keys[-1], value)


# Default configuration values
DEFAULT_CONFIG = {
    "llm": {
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "api_key_env": "ANTHROPIC_API_KEY",
        "max_tokens": 4096,
        "temperature": 0.1
    },
    "retrieval": {
        "top_k": 10,
        "candidate_pool_size": 50,
        "enable_two_stage_rerank": False,
        "keyword_weight": 0.3,
        "semantic_weight": 0.7
    },
    "context": {
        "max_files_per_commit": 10,
        "max_lines_per_file": 100,
        "max_total_commits": 5,
        "truncate_strategy": "head"
    },
    "index": {
        "max_commits": 1000,
        "branches": ["main", "master"],
        "batch_size": 100,
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536
    },
    "observability": {
        "log_level": "INFO",
        "enable_metrics": True,
        "log_file": None,
        "max_log_size_mb": 100
    }
}


def get_config_path(repo_root: Path) -> Path:
    """
    Get the path to the config file.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Path to the config file.
    """
    return repo_root / ".gimi" / "config.json"


def load_config(repo_root: Path) -> GimiConfig:
    """
    Load configuration from .gimi/config.json.

    If the config file doesn't exist or is invalid, returns the default
    configuration.

    Args:
        repo_root: Path to the repository root.

    Returns:
        GimiConfig object.
    """
    config_path = get_config_path(repo_root)

    if not config_path.exists():
        return GimiConfig()

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            loaded_config = json.load(f)

        # Convert to GimiConfig
        return GimiConfig._from_dict(loaded_config)
    except json.JSONDecodeError as e:
        # Invalid JSON, return defaults
        return GimiConfig()
    except Exception as e:
        # Other errors, return defaults
        return GimiConfig()


def save_config(repo_root: Path, config: Dict[str, Any]) -> None:
    """
    Save configuration to .gimi/config.json.

    Args:
        repo_root: Path to the repository root.
        config: Configuration dictionary to save.

    Raises:
        ConfigError: If unable to save configuration.
    """
    config_path = get_config_path(repo_root)

    try:
        # Ensure parent directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, sort_keys=True)
    except Exception as e:
        raise ConfigError(f"Failed to save configuration: {e}")


def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two configuration dictionaries.

    Values from the override config take precedence over base config.
    Nested dictionaries are merged recursively.

    Args:
        base: Base configuration.
        override: Override configuration.

    Returns:
        Merged configuration.
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dicts
            result[key] = merge_configs(result[key], value)
        else:
            # Override value
            result[key] = value

    return result


def init_config(
    repo_root: Path,
    config_overrides: Optional[Dict[str, Any]] = None
) -> GimiConfig:
    """
    Initialize a new configuration for a repository.

    Args:
        repo_root: Path to the repository root.
        config_overrides: Optional configuration overrides.

    Returns:
        Initialized GimiConfig.

    Raises:
        ConfigError: If initialization fails.
    """
    try:
        # Start with default configuration
        config = GimiConfig()

        # Apply any overrides
        if config_overrides:
            config_dict = config.to_dict()
            merged = merge_configs(config_dict, config_overrides)
            config = GimiConfig._from_dict(merged)

        # Save the configuration
        save_config(repo_root, config.to_dict())

        return config

    except Exception as e:
        raise ConfigError(f"Failed to initialize configuration: {e}")


def get_config_value(
    config: Dict[str, Any],
    key_path: str,
    default: Any = None
) -> Any:
    """
    Get a configuration value by key path.

    Supports nested keys using dot notation (e.g., "llm.model").

    Args:
        config: Configuration dictionary.
        key_path: Key path (e.g., "llm.model" or "top_k").
        default: Default value if key not found.

    Returns:
        Configuration value, or default if not found.
    """
    keys = key_path.split('.')
    value = config

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def set_config_value(
    config: Dict[str, Any],
    key_path: str,
    value: Any
) -> None:
    """
    Set a configuration value by key path.

    Supports nested keys using dot notation (e.g., "llm.model").
    Creates intermediate dictionaries as needed.

    Args:
        config: Configuration dictionary.
        key_path: Key path (e.g., "llm.model" or "top_k").
        value: Value to set.
    """
    keys = key_path.split('.')
    target = config

    # Navigate to the parent of the target key
    for key in keys[:-1]:
        if key not in target:
            target[key] = {}
        target = target[key]

    # Set the value
    target[keys[-1]] = value
