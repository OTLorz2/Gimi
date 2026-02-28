"""
T17: 错误处理与文档

功能：
- 统一处理「非 git 目录」「锁失败」「索引损坏」「LLM 超时/限流」等错误
- 给出明确提示
- 编写 README/使用说明
"""

import sys
import traceback
from pathlib import Path
from typing import Optional, Type, Callable
from functools import wraps
from enum import Enum


class ErrorCode(Enum):
    """错误代码枚举"""
    # 环境错误 (1xx)
    NOT_GIT_REPO = 101
    GIT_COMMAND_FAILED = 102

    # 索引错误 (2xx)
    INDEX_CORRUPTED = 201
    INDEX_LOCKED = 202
    INDEX_BUILD_FAILED = 203

    # 检索错误 (3xx)
    RETRIEVAL_FAILED = 301
    NO_RESULTS_FOUND = 302

    # LLM 错误 (4xx)
    LLM_API_ERROR = 401
    LLM_TIMEOUT = 402
    LLM_RATE_LIMITED = 403
    LLM_CONTEXT_TOO_LONG = 404

    # 配置错误 (5xx)
    CONFIG_INVALID = 501
    CONFIG_MISSING = 502

    # 未知错误
    UNKNOWN_ERROR = 999


class GimiError(Exception):
    """Gimi 基础异常类"""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[dict] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        parts = [f"[{self.code.name}] {self.message}"]

        if self.details:
            parts.append(f"Details: {self.details}")

        if self.cause:
            parts.append(f"Caused by: {type(self.cause).__name__}: {self.cause}")

        return "\n".join(parts)


class ErrorHandler:
    """错误处理器"""

    # 错误消息模板
    ERROR_MESSAGES = {
        ErrorCode.NOT_GIT_REPO: {
            "message": "当前目录不在 git 仓库中",
            "suggestion": "请在 git 仓库内执行 gimi 命令，或使用 --repo 指定仓库路径。",
        },
        ErrorCode.GIT_COMMAND_FAILED: {
            "message": "Git 命令执行失败",
            "suggestion": "请检查 git 是否已安装，以及当前目录是否在有效的 git 仓库中。",
        },
        ErrorCode.INDEX_CORRUPTED: {
            "message": "索引文件已损坏",
            "suggestion": "请运行 'gimi index --rebuild' 重建索引。",
        },
        ErrorCode.INDEX_LOCKED: {
            "message": "索引正在被其他进程使用",
            "suggestion": "请等待其他 gimi 进程完成，或手动删除 .gimi/write.lock 文件。",
        },
        ErrorCode.INDEX_BUILD_FAILED: {
            "message": "索引构建失败",
            "suggestion": "请检查 git 仓库状态，或查看 .gimi/logs/ 目录下的错误日志。",
        },
        ErrorCode.RETRIEVAL_FAILED: {
            "message": "检索过程发生错误",
            "suggestion": "请检查索引是否已构建，或尝试重建索引。",
        },
        ErrorCode.NO_RESULTS_FOUND: {
            "message": "未找到匹配的 commit",
            "suggestion": "请尝试修改查询条件，或检查仓库是否有足够的 commit 历史。",
        },
        ErrorCode.LLM_API_ERROR: {
            "message": "LLM API 调用失败",
            "suggestion": "请检查 API key 是否正确配置，以及网络连接是否正常。",
        },
        ErrorCode.LLM_TIMEOUT: {
            "message": "LLM API 调用超时",
            "suggestion": "请稍后重试，或考虑使用更快的模型。",
        },
        ErrorCode.LLM_RATE_LIMITED: {
            "message": "LLM API 调用频率超限",
            "suggestion": "请稍等片刻后重试，或升级您的 API 套餐。",
        },
        ErrorCode.LLM_CONTEXT_TOO_LONG: {
            "message": "Prompt 超出模型上下文长度限制",
            "suggestion": "请尝试缩小检索范围，或选择支持更长上下文的模型。",
        },
        ErrorCode.CONFIG_INVALID: {
            "message": "配置文件无效",
            "suggestion": "请检查 .gimi/config.json 文件格式是否正确。",
        },
        ErrorCode.CONFIG_MISSING: {
            "message": "缺少必要的配置项",
            "suggestion": "请运行 'gimi config' 进行配置，或手动编辑 .gimi/config.json。",
        },
        ErrorCode.UNKNOWN_ERROR: {
            "message": "发生未知错误",
            "suggestion": "请查看 .gimi/logs/ 目录下的错误日志，或提交 issue 报告问题。",
        },
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def handle(self, error: Exception, exit_on_error: bool = True) -> None:
        """
        处理异常

        Args:
            error: 异常对象
            exit_on_error: 是否在处理后退出程序
        """
        if isinstance(error, GimiError):
            self._handle_gimi_error(error)
        else:
            self._handle_generic_error(error)

        if exit_on_error:
            code = self._get_exit_code(error)
            sys.exit(code)

    def _handle_gimi_error(self, error: GimiError) -> None:
        """处理 GimiError"""
        template = self.ERROR_MESSAGES.get(error.code, self.ERROR_MESSAGES[ErrorCode.UNKNOWN_ERROR])

        print(f"错误 [{error.code.value}]: {template['message']}", file=sys.stderr)

        if error.message != template['message']:
            print(f"详细信息: {error.message}", file=sys.stderr)

        if error.details:
            print(f"上下文: {error.details}", file=sys.stderr)

        print(f"\n建议: {template['suggestion']}", file=sys.stderr)

        if self.verbose and error.cause:
            print(f"\n原始异常:", file=sys.stderr)
            traceback.print_exception(type(error.cause), error.cause, error.cause.__traceback__)

    def _handle_generic_error(self, error: Exception) -> None:
        """处理通用异常"""
        print(f"发生未处理的异常: {type(error).__name__}: {error}", file=sys.stderr)

        if self.verbose:
            traceback.print_exception(type(error), error, error.__traceback__)

        print("\n建议: 请查看 .gimi/logs/ 目录下的错误日志，或提交 issue 报告问题。", file=sys.stderr)

    def _get_exit_code(self, error: Exception) -> int:
        """获取退出码"""
        if isinstance(error, GimiError):
            return error.code.value
        return 999


def safe_execute(
    func: Callable,
    *args,
    error_handler: Optional[ErrorHandler] = None,
    exit_on_error: bool = True,
    **kwargs
):
    """
    安全执行函数，自动处理异常

    Args:
        func: 要执行的函数
        error_handler: 错误处理器，默认创建新实例
        exit_on_error: 出错时是否退出
        *args, **kwargs: 传递给函数的参数

    Returns:
        函数的返回值
    """
    handler = error_handler or ErrorHandler()

    try:
        return func(*args, **kwargs)
    except Exception as e:
        handler.handle(e, exit_on_error=exit_on_error)
        return None


if __name__ == "__main__":
    print("测试错误处理...")

    # 测试错误消息
    handler = ErrorHandler(verbose=True)

    # 测试 GimiError
    print("\n测试 GimiError...")

    error = GimiError(
        message="自定义错误消息",
        code=ErrorCode.INDEX_CORRUPTED,
        details={"file": "test.db"},
    )

    handler._handle_gimi_error(error)

    # 测试通用错误
    print("\n测试通用错误...")

    try:
        raise ValueError("测试异常")
    except Exception as e:
        handler._handle_generic_error(e)

    print("\n错误处理测试完成!")
