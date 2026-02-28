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
from pathlib import Path
from typing import Any, Dict, Optional, Union


class ConfigError(Exception):
    """Error related to configuration operations."""
    pass


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


def load_config(repo_root: Path) -> Dict[str, Any]:
    """
    Load configuration from .gimi/config.json.

    If the config file doesn't exist or is invalid, returns the default
    configuration.

    Args:
        repo_root: Path to the repository root.

    Returns:
        Configuration dictionary.
    """
    config_path = get_config_path(repo_root)

    if not config_path.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            loaded_config = json.load(f)

        # Merge with defaults
        return merge_configs(DEFAULT_CONFIG.copy(), loaded_config)
    except json.JSONDecodeError as e:
        # Invalid JSON, return defaults
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        # Other errors, return defaults
        return DEFAULT_CONFIG.copy()


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
