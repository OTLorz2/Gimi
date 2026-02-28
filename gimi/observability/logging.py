"""Logging and observability for Gimi.

This module provides structured logging for requests, index builds, and errors.
"""

import json
import time
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


@dataclass
class RequestLogEntry:
    """Log entry for a single request."""
    request_id: str
    timestamp: str
    repo_root: str
    query: str
    file_path: Optional[str]
    branch: Optional[str]
    success: bool
    error: Optional[str] = None
    candidate_count: int = 0
    top_k: int = 0
    diff_count: int = 0
    llm_duration: float = 0.0


@dataclass
class IndexBuildLogEntry:
    """Log entry for index build operations."""
    build_id: str
    timestamp: str
    repo_root: str
    success: bool
    error: Optional[str] = None
    commit_count: int = 0
    branch_count: int = 0
    duration_seconds: float = 0.0


class RequestLogger:
    """Logger for Gimi requests."""

    def __init__(self, gimi_dir: Path):
        """
        Initialize the logger.

        Args:
            gimi_dir: Path to .gimi directory
        """
        self.gimi_dir = Path(gimi_dir)
        self.logs_dir = self.gimi_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.requests_log = self.logs_dir / "requests.jsonl"
        self.errors_log = self.logs_dir / "errors.log"

    def start_request(
        self,
        repo_root: str,
        query: str,
        file_path: Optional[str] = None,
        branch: Optional[str] = None
    ) -> str:
        """
        Start logging a new request.

        Args:
            repo_root: Path to repository root
            query: User query
            file_path: Optional file path filter
            branch: Optional branch filter

        Returns:
            Request ID
        """
        request_id = str(uuid.uuid4())

        # Store request info for later completion
        self._current_request = {
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat(),
            "repo_root": repo_root,
            "query": query,
            "file_path": file_path,
            "branch": branch,
        }

        return request_id

    def end_request(
        self,
        request_id: str,
        success: bool,
        error: Optional[str] = None,
        candidate_count: int = 0,
        top_k: int = 0,
        diff_count: int = 0,
        llm_duration: float = 0.0
    ) -> None:
        """
        Complete logging a request.

        Args:
            request_id: Request ID from start_request
            success: Whether the request was successful
            error: Optional error message
            candidate_count: Number of candidates found
            top_k: Number of top commits selected
            diff_count: Number of diffs fetched
            llm_duration: LLM call duration in seconds
        """
        if not hasattr(self, "_current_request"):
            return

        entry = RequestLogEntry(
            request_id=request_id,
            timestamp=self._current_request.get("timestamp", datetime.utcnow().isoformat()),
            repo_root=self._current_request.get("repo_root", ""),
            query=self._current_request.get("query", ""),
            file_path=self._current_request.get("file_path"),
            branch=self._current_request.get("branch"),
            success=success,
            error=error,
            candidate_count=candidate_count,
            top_k=top_k,
            diff_count=diff_count,
            llm_duration=llm_duration
        )

        # Write to JSONL file
        try:
            with open(self.requests_log, "a", encoding="utf-8") as f:
                json.dump(asdict(entry), f)
                f.write("\n")
        except Exception:
            pass

        # Also log errors separately
        if not success and error:
            try:
                with open(self.errors_log, "a", encoding="utf-8") as f:
                    timestamp = datetime.utcnow().isoformat()
                    f.write(f"[{timestamp}] {request_id}: {error}\n")
            except Exception:
                pass


class IndexBuildLogger:
    """Logger for index build operations."""

    def __init__(self, gimi_dir: Path):
        """
        Initialize the logger.

        Args:
            gimi_dir: Path to .gimi directory
        """
        self.gimi_dir = Path(gimi_dir)
        self.logs_dir = self.gimi_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.builds_log = self.logs_dir / "index_builds.jsonl"

    def log_build(
        self,
        repo_root: str,
        success: bool,
        error: Optional[str] = None,
        commit_count: int = 0,
        branch_count: int = 0,
        duration_seconds: float = 0.0
    ) -> str:
        """
        Log an index build operation.

        Args:
            repo_root: Path to repository root
            success: Whether the build was successful
            error: Optional error message
            commit_count: Number of commits indexed
            branch_count: Number of branches indexed
            duration_seconds: Build duration in seconds

        Returns:
            Build ID
        """
        build_id = str(uuid.uuid4())

        entry = IndexBuildLogEntry(
            build_id=build_id,
            timestamp=datetime.utcnow().isoformat(),
            repo_root=repo_root,
            success=success,
            error=error,
            commit_count=commit_count,
            branch_count=branch_count,
            duration_seconds=duration_seconds
        )

        try:
            with open(self.builds_log, "a", encoding="utf-8") as f:
                json.dump(asdict(entry), f)
                f.write("\n")
        except Exception:
            pass

        return build_id
