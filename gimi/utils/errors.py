"""
错误处理模块
提供统一的错误处理和用户友好的错误提示
"""

import sys
import traceback
from typing import Optional


class GimiError(Exception):
    """Gimi基础异常类"""

    def __init__(
        self,
        message: str,
        error_code: str = "UNKNOWN",
        suggestion: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.suggestion = suggestion

    def __str__(self) -> str:
        parts = [f"[{self.error_code}] {self.message}"]
        if self.suggestion:
            parts.append(f"建议: {self.suggestion}")
        return "\n".join(parts)


class GitNotFoundError(GimiError):
    """Git未找到错误"""

    def __init__(self):
        super().__init__(
            message="未找到Git命令",
            error_code="GIT_NOT_FOUND",
            suggestion="请确保Git已安装并添加到系统PATH中",
        )


class NotGitRepositoryError(GimiError):
    """非Git仓库错误"""

    def __init__(self, path: str):
        super().__init__(
            message=f"'{path}' 不是Git仓库",
            error_code="NOT_GIT_REPO",
            suggestion="请在Git仓库内执行此命令，或先执行 'git init' 初始化仓库",
        )


class IndexNotFoundError(GimiError):
    """索引不存在错误"""

    def __init__(self):
        super().__init__(
            message="索引不存在",
            error_code="INDEX_NOT_FOUND",
            suggestion="请先执行 'gimi index' 构建索引",
        )


class IndexExpiredError(GimiError):
    """索引过期错误"""

    def __init__(self, reason: str):
        super().__init__(
            message=f"索引已过期: {reason}",
            error_code="INDEX_EXPIRED",
            suggestion="请执行 'gimi index --force' 重建索引",
        )


class LockError(GimiError):
    """锁错误"""

    def __init__(self, resource: str, reason: str = ""):
        message = f"无法获取资源锁: {resource}"
        if reason:
            message += f" ({reason})"

        super().__init__(
            message=message,
            error_code="LOCK_ERROR",
            suggestion="可能有其他gimi进程正在运行，请稍后再试",
        )


class LLMError(GimiError):
    """LLM调用错误"""

    def __init__(self, provider: str, message: str):
        super().__init__(
            message=f"{provider} API调用失败: {message}",
            error_code="LLM_ERROR",
            suggestion="请检查API密钥和网络连接，或稍后再试",
        )


class ConfigError(GimiError):
    """配置错误"""

    def __init__(self, message: str):
        super().__init__(
            message=f"配置错误: {message}",
            error_code="CONFIG_ERROR",
            suggestion="请检查配置文件格式或删除重新配置",
        )


def handle_error(error: Exception, verbose: bool = False) -> int:
    """
    统一错误处理

    Args:
        error: 异常对象
        verbose: 是否显示详细错误信息

    Returns:
        退出码
    """
    if isinstance(error, GimiError):
        # Gimi自定义错误，显示友好提示
        print(f"[ERROR] {error.message}", file=sys.stderr)
        if error.suggestion:
            print(f"[提示] {error.suggestion}", file=sys.stderr)

        # 根据错误类型返回不同退出码
        error_codes = {
            "GIT_NOT_FOUND": 10,
            "NOT_GIT_REPO": 11,
            "INDEX_NOT_FOUND": 20,
            "INDEX_EXPIRED": 21,
            "LOCK_ERROR": 30,
            "LLM_ERROR": 40,
            "CONFIG_ERROR": 50,
        }
        return error_codes.get(error.error_code, 1)

    elif isinstance(error, KeyboardInterrupt):
        print("\n[WARNING] 操作已取消", file=sys.stderr)
        return 130

    else:
        # 未知错误
        print(f"[ERROR] 发生未知错误: {error}", file=sys.stderr)

        if verbose:
            print("\n详细错误信息:", file=sys.stderr)
            traceback.print_exc()

        return 1


def safe_execute(func, *args, verbose: bool = False, **kwargs):
    """
    安全执行函数，自动处理异常

    Args:
        func: 要执行的函数
        *args: 位置参数
        verbose: 是否显示详细错误
        **kwargs: 关键字参数

    Returns:
        函数返回值，出错时返回None
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        handle_error(e, verbose=verbose)
        return None
