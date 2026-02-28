"""Structured logging for Gimi observability."""

import json
import uuid
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import sys


@dataclass
class RequestLog:
    """Log entry for a single request."""
    request_id: str
    timestamp: str
    repo_root: str
    query: str
    index_valid: bool
    index_rebuilt: bool
    candidate_count: int
    top_k_count: int
    context_tokens: int
    llm_model: str
    llm_latency_ms: float
    response_status: str
    error_message: Optional[str] = None
    files_specified: Optional[List[str]] = None
    branch_specified: Optional[str] = None
    referenced_commits: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class IndexBuildLog:
    """Log entry for index building."""
    request_id: str
    timestamp: str
    repo_root: str
    branches: List[str]
    commits_indexed: int
    duration_ms: float
    incremental: bool
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class GimiLogger:
    """Structured logger for Gimi operations."""

    def __init__(self, logs_dir: Path, request_id: Optional[str] = None):
        """
        Initialize logger.

        Args:
            logs_dir: Directory for log files
            request_id: Optional request ID (generated if not provided)
        """
        self.logs_dir = logs_dir
        self.request_id = request_id or str(uuid.uuid4())[:8]
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Create log files
        self.requests_log = self.logs_dir / "requests.jsonl"
        self.index_log = self.logs_dir / "index_builds.jsonl"
        self.error_log = self.logs_dir / "errors.log"

        # Setup Python logger for errors
        self._error_logger = logging.getLogger(f"gimi.{self.request_id}")
        self._error_logger.setLevel(logging.DEBUG)

        # File handler for errors
        fh = logging.FileHandler(self.error_log)
        fh.setLevel(logging.ERROR)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        fh.setFormatter(formatter)
        self._error_logger.addHandler(fh)

        # Console handler for warnings
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        self._error_logger.addHandler(ch)

    def log_request(
        self,
        repo_root: str,
        query: str,
        index_valid: bool,
        index_rebuilt: bool,
        candidate_count: int,
        top_k_count: int,
        context_tokens: int,
        llm_model: str,
        llm_latency_ms: float,
        response_status: str,
        error_message: Optional[str] = None,
        files_specified: Optional[List[str]] = None,
        branch_specified: Optional[str] = None,
        referenced_commits: Optional[List[str]] = None
    ) -> None:
        """Log a request."""
        log_entry = RequestLog(
            request_id=self.request_id,
            timestamp=datetime.utcnow().isoformat(),
            repo_root=repo_root,
            query=query,
            index_valid=index_valid,
            index_rebuilt=index_rebuilt,
            candidate_count=candidate_count,
            top_k_count=top_k_count,
            context_tokens=context_tokens,
            llm_model=llm_model,
            llm_latency_ms=llm_latency_ms,
            response_status=response_status,
            error_message=error_message,
            files_specified=files_specified,
            branch_specified=branch_specified,
            referenced_commits=referenced_commits
        )

        with open(self.requests_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry.to_dict()) + "\n")

        if error_message:
            self._error_logger.error(
                f"Request {self.request_id} failed: {error_message}"
            )

    def log_index_build(
        self,
        repo_root: str,
        branches: List[str],
        commits_indexed: int,
        duration_ms: float,
        incremental: bool = False,
        error_message: Optional[str] = None
    ) -> None:
        """Log an index build."""
        log_entry = IndexBuildLog(
            request_id=self.request_id,
            timestamp=datetime.utcnow().isoformat(),
            repo_root=repo_root,
            branches=branches,
            commits_indexed=commits_indexed,
            duration_ms=duration_ms,
            incremental=incremental,
            error_message=error_message
        )

        with open(self.index_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry.to_dict()) + "\n")

    def log_error(self, message: str, exc_info: bool = False) -> None:
        """Log an error."""
        self._error_logger.error(message, exc_info=exc_info)

    def log_warning(self, message: str) -> None:
        """Log a warning."""
        self._error_logger.warning(message)

    def log_info(self, message: str) -> None:
        """Log info message."""
        self._error_logger.info(message)

    def get_request_id(self) -> str:
        """Get the request ID."""
        return self.request_id
