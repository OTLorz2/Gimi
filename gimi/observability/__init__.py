"""Observability module for Gimi - logging and monitoring.

This module provides logging and observability features for the Gimi
application, including request logging, index build logging, and
telemetry collection.
"""

# Import main classes for easy access
from gimi.observability.logging import (
    RequestLogger,
    IndexBuildLogger,
    RequestLogEntry,
    IndexBuildLogEntry,
)

__all__ = [
    "RequestLogger",
    "IndexBuildLogger",
    "RequestLogEntry",
    "IndexBuildLogEntry",
]