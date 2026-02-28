"""Custom exceptions for Gimi.

This module defines all custom exception types used throughout
the Gimi codebase. These exceptions provide specific error types
for different failure scenarios, making error handling more
explicit and informative.
"""


class GimiError(Exception):
    """Base exception for all Gimi errors."""

    def __init__(self, message: str, details: dict = None):
        """Initialize the error.

        Args:
            message: Human-readable error message
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


# Repository-related errors
class RepoError(GimiError):
    """Raised when repository operations fail."""
    pass


class NotAGitRepositoryError(RepoError):
    """Raised when not inside a git repository."""

    def __init__(self, path: str = None):
        message = "Not a git repository (or any of the parent directories): .git"
        details = {"path": path} if path else {}
        super().__init__(message, details)


class GitCommandError(RepoError):
    """Raised when a git command fails."""

    def __init__(self, command: str, returncode: int, stderr: str = None):
        message = f"Git command failed: {command}"
        details = {
            "command": command,
            "returncode": returncode,
            "stderr": stderr
        }
        super().__init__(message, details)


# Lock-related errors
class LockError(GimiError):
    """Raised when lock operations fail."""
    pass


class LockAcquisitionError(LockError):
    """Raised when unable to acquire a lock."""

    def __init__(self, lock_file: str, pid: int = None):
        message = f"Could not acquire lock on {lock_file}"
        details = {"lock_file": lock_file, "holding_pid": pid}
        super().__init__(message, details)


class StaleLockError(LockError):
    """Raised when a stale lock is detected."""

    def __init__(self, lock_file: str, pid: int):
        message = f"Detected stale lock file: {lock_file} (PID {pid} not running)"
        details = {"lock_file": lock_file, "pid": pid}
        super().__init__(message, details)


# Configuration errors
class ConfigError(GimiError):
    """Raised when configuration operations fail."""
    pass


class ConfigLoadError(ConfigError):
    """Raised when configuration cannot be loaded."""

    def __init__(self, config_path: str, reason: str = None):
        message = f"Failed to load configuration from {config_path}"
        if reason:
            message += f": {reason}"
        details = {"config_path": config_path, "reason": reason}
        super().__init__(message, details)


class ConfigValidationError(ConfigError):
    """Raised when configuration validation fails."""

    def __init__(self, field: str, value: any, expected: str = None):
        message = f"Invalid configuration value for '{field}': {value}"
        if expected:
            message += f" (expected: {expected})"
        details = {"field": field, "value": value, "expected": expected}
        super().__init__(message, details)


# Index-related errors
class IndexError(GimiError):
    """Raised when index operations fail."""
    pass


class IndexBuildError(IndexError):
    """Raised when index building fails."""

    def __init__(self, reason: str, phase: str = None):
        message = f"Failed to build index: {reason}"
        details = {"reason": reason, "phase": phase}
        super().__init__(message, details)


class IndexNotFoundError(IndexError):
    """Raised when requested index does not exist."""

    def __init__(self, index_path: str, index_type: str = None):
        message = f"Index not found: {index_path}"
        details = {"index_path": index_path, "index_type": index_type}
        super().__init__(message, details)


class IndexCorruptedError(IndexError):
    """Raised when index is corrupted or invalid."""

    def __init__(self, index_path: str, reason: str = None):
        message = f"Index is corrupted: {index_path}"
        if reason:
            message += f" ({reason})"
        details = {"index_path": index_path, "reason": reason}
        super().__init__(message, details)


class IndexOutdatedError(IndexError):
    """Raised when index is outdated compared to repository."""

    def __init__(self, index_refs: dict, current_refs: dict):
        message = "Index is outdated and needs to be rebuilt"
        details = {
            "index_refs": index_refs,
            "current_refs": current_refs,
            "changed_refs": [
                ref for ref in current_refs
                if ref in index_refs and index_refs[ref] != current_refs[ref]
            ]
        }
        super().__init__(message, details)


# Embedding errors
class EmbeddingError(GimiError):
    """Raised when embedding operations fail."""
    pass


class EmbeddingModelError(EmbeddingError):
    """Raised when embedding model fails to load or run."""

    def __init__(self, model_name: str, reason: str):
        message = f"Embedding model '{model_name}' failed: {reason}"
        details = {"model_name": model_name, "reason": reason}
        super().__init__(message, details)


class EmbeddingAPIError(EmbeddingError):
    """Raised when embedding API call fails."""

    def __init__(self, api_name: str, status_code: int, response: str = None):
        message = f"Embedding API '{api_name}' returned error {status_code}"
        details = {
            "api_name": api_name,
            "status_code": status_code,
            "response": response
        }
        super().__init__(message, details)


class EmbeddingDimensionError(EmbeddingError):
    """Raised when embedding dimension mismatch occurs."""

    def __init__(self, expected: int, actual: int, context: str = None):
        message = f"Embedding dimension mismatch: expected {expected}, got {actual}"
        details = {"expected": expected, "actual": actual, "context": context}
        super().__init__(message, details)


# LLM-related errors
class LLMError(GimiError):
    """Raised when LLM operations fail."""
    pass


class LLMConnectionError(LLMError):
    """Raised when connection to LLM service fails."""

    def __init__(self, provider: str, api_base: str, reason: str = None):
        message = f"Failed to connect to {provider} at {api_base}"
        if reason:
            message += f": {reason}"
        details = {"provider": provider, "api_base": api_base, "reason": reason}
        super().__init__(message, details)


class LLMRateLimitError(LLMError):
    """Raised when LLM API rate limit is exceeded."""

    def __init__(self, provider: str, retry_after: int = None):
        message = f"Rate limit exceeded for {provider}"
        if retry_after:
            message += f". Retry after {retry_after} seconds."
        details = {"provider": provider, "retry_after": retry_after}
        super().__init__(message, details)


class LLMTokenLimitError(LLMError):
    """Raised when token limit is exceeded."""

    def __init__(self, prompt_tokens: int, max_tokens: int, model: str = None):
        message = f"Prompt too long: {prompt_tokens} tokens exceeds limit of {max_tokens}"
        details = {
            "prompt_tokens": prompt_tokens,
            "max_tokens": max_tokens,
            "model": model
        }
        super().__init__(message, details)


class LLMResponseError(LLMError):
    """Raised when LLM returns an invalid or unexpected response."""

    def __init__(self, provider: str, response: str = None, reason: str = None):
        message = f"Invalid response from {provider}"
        if reason:
            message += f": {reason}"
        details = {"provider": provider, "response": response, "reason": reason}
        super().__init__(message, details)


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""

    def __init__(self, provider: str, timeout: float):
        message = f"Request to {provider} timed out after {timeout} seconds"
        details = {"provider": provider, "timeout": timeout}
        super().__init__(message, details)


# Context-related errors
class ContextError(GimiError):
    """Raised when context assembly fails."""
    pass


class ContextTruncationError(ContextError):
    """Raised when context cannot fit within limits."""

    def __init__(self, original_size: int, max_size: int, content_type: str = None):
        message = f"Could not fit content within limits: {original_size} > {max_size}"
        details = {
            "original_size": original_size,
            "max_size": max_size,
            "content_type": content_type
        }
        super().__init__(message, details)


class DiffError(ContextError):
    """Raised when diff operations fail."""
    pass


class DiffNotFoundError(DiffError):
    """Raised when a diff cannot be found."""

    def __init__(self, commit_hash: str, reason: str = None):
        message = f"Diff not found for commit {commit_hash}"
        if reason:
            message += f": {reason}"
        details = {"commit_hash": commit_hash, "reason": reason}
        super().__init__(message, details)


class DiffParseError(DiffError):
    """Raised when diff parsing fails."""

    def __init__(self, commit_hash: str, reason: str):
        message = f"Failed to parse diff for {commit_hash}: {reason}"
        details = {"commit_hash": commit_hash, "reason": reason}
        super().__init__(message, details)


# Cache-related errors
class CacheError(GimiError):
    """Raised when cache operations fail."""
    pass


class CacheReadError(CacheError):
    """Raised when cache read fails."""

    def __init__(self, cache_path: str, reason: str):
        message = f"Failed to read cache from {cache_path}: {reason}"
        details = {"cache_path": cache_path, "reason": reason}
        super().__init__(message, details)


class CacheWriteError(CacheError):
    """Raised when cache write fails."""

    def __init__(self, cache_path: str, reason: str):
        message = f"Failed to write cache to {cache_path}: {reason}"
        details = {"cache_path": cache_path, "reason": reason}
        super().__init__(message, details)


class CacheCorruptedError(CacheError):
    """Raised when cache is corrupted."""

    def __init__(self, cache_path: str, reason: str):
        message = f"Cache is corrupted: {cache_path}"
        details = {"cache_path": cache_path, "reason": reason}
        super().__init__(message, details)
