"""
日志记录模块
提供可观测的日志记录功能
"""

import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """JSON格式日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加额外字段
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "repo_root"):
            log_data["repo_root"] = str(record.repo_root)
        if hasattr(record, "operation"):
            log_data["operation"] = record.operation
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


class GimiLogger:
    """
    Gimi专用日志记录器

    提供结构化日志记录，支持:
    - 请求追踪(request_id)
    - 性能计时(duration_ms)
    - 操作类型标记(operation)
    """

    def __init__(
        self,
        name: str = "gimi",
        log_dir: Optional[Path] = None,
        log_level: str = "INFO",
        enable_console: bool = True,
        enable_file: bool = True,
    ):
        self.name = name
        self.log_dir = log_dir
        self.log_level = getattr(logging, log_level.upper())
        self.enable_console = enable_console
        self.enable_file = enable_file

        self._logger = logging.getLogger(name)
        self._logger.setLevel(self.log_level)
        self._logger.handlers = []  # 清除已有handlers

        self._setup_handlers()

        # 当前请求上下文
        self._current_request_id: Optional[str] = None
        self._current_repo_root: Optional[Path] = None

    def _setup_handlers(self):
        """设置日志处理器"""
        formatter = JSONFormatter()

        # 控制台输出
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            # 控制台使用简单格式
            simple_formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s"
            )
            console_handler.setFormatter(simple_formatter)
            self._logger.addHandler(console_handler)

        # 文件输出
        if self.enable_file and self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

            # 主日志文件
            log_file = self.log_dir / "gimi.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

            # 错误日志文件
            error_log_file = self.log_dir / "error.log"
            error_handler = logging.FileHandler(error_log_file, encoding="utf-8")
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            self._logger.addHandler(error_handler)

    def set_request_context(
        self,
        request_id: Optional[str] = None,
        repo_root: Optional[Path] = None,
    ):
        """设置当前请求上下文"""
        self._current_request_id = request_id or str(uuid.uuid4())[:8]
        self._current_repo_root = repo_root

    def clear_request_context(self):
        """清除请求上下文"""
        self._current_request_id = None
        self._current_repo_root = None

    def _make_extra(self, **kwargs) -> dict:
        """构建extra字典"""
        extra = {}

        if self._current_request_id:
            extra["request_id"] = self._current_request_id
        if self._current_repo_root:
            extra["repo_root"] = str(self._current_repo_root)

        extra.update(kwargs)
        return extra

    def debug(self, message: str, **kwargs):
        """记录DEBUG级别日志"""
        extra = self._make_extra(**kwargs)
        self._logger.debug(message, extra=extra)

    def info(self, message: str, **kwargs):
        """记录INFO级别日志"""
        extra = self._make_extra(**kwargs)
        self._logger.info(message, extra=extra)

    def warning(self, message: str, **kwargs):
        """记录WARNING级别日志"""
        extra = self._make_extra(**kwargs)
        self._logger.warning(message, extra=extra)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        """记录ERROR级别日志"""
        extra = self._make_extra(**kwargs)
        self._logger.error(message, exc_info=exc_info, extra=extra)

    def critical(self, message: str, exc_info: bool = False, **kwargs):
        """记录CRITICAL级别日志"""
        extra = self._make_extra(**kwargs)
        self._logger.critical(message, exc_info=exc_info, extra=extra)

    def log_operation(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        **kwargs,
    ):
        """记录操作日志"""
        status = "成功" if success else "失败"
        message = f"操作 [{operation}] {status}, 耗时 {duration_ms:.2f}ms"

        extra = self._make_extra(
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            **kwargs,
        )

        if success:
            self.info(message, **extra)
        else:
            self.error(message, **extra)


# 全局日志记录器实例
_global_logger: Optional[GimiLogger] = None


def get_logger(
    log_dir: Optional[Path] = None,
    log_level: str = "INFO",
) -> GimiLogger:
    """
    获取全局日志记录器

    Args:
        log_dir: 日志目录
        log_level: 日志级别

    Returns:
        GimiLogger实例
    """
    global _global_logger

    if _global_logger is None:
        _global_logger = GimiLogger(
            log_dir=log_dir,
            log_level=log_level,
            enable_console=True,
            enable_file=log_dir is not None,
        )

    return _global_logger


def set_request_context(
    request_id: Optional[str] = None,
    repo_root: Optional[Path] = None,
) -> str:
    """
    设置请求上下文

    Returns:
        request_id
    """
    global _global_logger

    if _global_logger is None:
        # 初始化一个基本logger
        _global_logger = GimiLogger(enable_file=False)

    req_id = request_id or str(uuid.uuid4())[:8]
    _global_logger.set_request_context(req_id, repo_root)
    return req_id


def clear_request_context():
    """清除请求上下文"""
    global _global_logger
    if _global_logger:
        _global_logger.clear_request_context()
