"""
T13: 取 diff 与截断

功能：
- 对 Top-K 的每个 commit 执行 `git show`（或读 cache）
- 按配置做截断（每文件行数、每 commit 文件数）
- 输出结构化「commit + 截断后 diff」供 T14 使用
"""

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime

from gimi.config import TruncateConfig


@dataclass
class FileDiff:
    """文件 diff 结构"""
    path: str
    change_type: str  # added, deleted, modified, renamed
    added_lines: int
    deleted_lines: int
    content: str  # 截断后的内容
    is_truncated: bool


@dataclass
class CommitDiff:
    """Commit diff 结构"""
    commit_hash: str
    short_hash: str
    message: str
    author_name: str
    author_date: datetime
    files: List[FileDiff]
    is_truncated: bool
    total_additions: int
    total_deletions: int
    estimated_tokens: int


def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量

    使用简单的启发式：平均每个词约 1.3 个 token
    """
    # 中文字符按字计数，英文按词计数
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))

    total_tokens = int((chinese_chars + english_words * 1.3) * 1.2)
    return total_tokens


class DiffBuilder:
    """Diff 构建器"""

    def __init__(
        self,
        repo_root: Path,
        config: Optional[TruncateConfig] = None,
    ):
        self.repo_root = Path(repo_root)
        self.config = config or TruncateConfig()

    def _run_git(self, args: List[str]) -> subprocess.CompletedProcess:
        """运行 git 命令"""
        result = subprocess.run(
            ["git"] + args,
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result

    def get_commit_info(self, commit_hash: str) -> Optional[Dict]:
        """获取 commit 基本信息"""
        result = self._run_git([
            "show",
            "--format=%H%n%h%n%s%n%an%n%ae%n%at",
            "--no-patch",
            commit_hash,
        ])

        if result.returncode != 0:
            return None

        lines = result.stdout.strip().split("\n")
        if len(lines) < 6:
            return None

        return {
            "hash": lines[0],
            "short_hash": lines[1],
            "message": lines[2],
            "author_name": lines[3],
            "author_email": lines[4],
            "author_date": datetime.fromtimestamp(int(lines[5])),
        }

    def get_diff_stats(self, commit_hash: str) -> Dict:
        """获取 diff 统计信息"""
        result = self._run_git([
            "show",
            "--stat",
            "--format=",
            commit_hash,
        ])

        stats = {
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
        }

        if result.returncode != 0 or not result.stdout:
            return stats

        # 解析统计信息
        lines = result.stdout.strip().split("\n")
        for line in lines:
            # 匹配 "5 files changed, 100 insertions(+), 20 deletions(-)"
            if "file" in line and "changed" in line:
                parts = line.split(",")
                for part in parts:
                    part = part.strip()
                    if "file" in part:
                        try:
                            stats["files_changed"] = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "insertion" in part:
                        try:
                            stats["insertions"] = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif "deletion" in part:
                        try:
                            stats["deletions"] = int(part.split()[0])
                        except (ValueError, IndexError):
                            pass

        return stats

    def get_file_diff(
        self,
        commit_hash: str,
        file_path: str,
        max_lines: Optional[int] = None,
    ) -> Optional[FileDiff]:
        """获取单个文件的 diff"""
        max_lines = max_lines or self.config.max_lines_per_file

        result = self._run_git([
            "show",
            commit_hash,
            "--",
            file_path,
        ])

        if result.returncode != 0:
            return None

        content = result.stdout

        # 解析 diff 头部信息
        added_lines = content.count("\n+")
        deleted_lines = content.count("\n-")

        # 确定变更类型
        change_type = "modified"
        if "new file" in content:
            change_type = "added"
        elif "deleted" in content:
            change_type = "deleted"
        elif "rename" in content or "similarity" in content:
            change_type = "renamed"

        # 截断内容
        lines = content.split("\n")
        is_truncated = len(lines) > max_lines

        if is_truncated:
            # 保留头部和尾部的行
            head_lines = max_lines // 2
            tail_lines = max_lines - head_lines
            kept_lines = lines[:head_lines] + ["... (truncated) ..."] + lines[-tail_lines:]
            content = "\n".join(kept_lines)
        else:
            content = "\n".join(lines)

        return FileDiff(
            path=file_path,
            change_type=change_type,
            added_lines=added_lines,
            deleted_lines=deleted_lines,
            content=content,
            is_truncated=is_truncated,
        )

    def build_commit_diff(
        self,
        commit_hash: str,
    ) -> Optional[CommitDiff]:
        """
        构建完整的 commit diff（带截断）

        Args:
            commit_hash: commit hash

        Returns:
            Optional[CommitDiff]: 截断后的 commit diff
        """
        # 获取基本信息
        info = self.get_commit_info(commit_hash)
        if not info:
            return None

        stats = self.get_diff_stats(commit_hash)

        # 获取文件列表
        result = self._run_git([
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit_hash,
        ])

        if result.returncode != 0:
            return None

        file_paths = [f for f in result.stdout.strip().split("\n") if f]

        # 限制文件数量
        max_files = self.config.max_files_per_commit
        is_truncated = len(file_paths) > max_files
        kept_files = file_paths[:max_files]

        # 获取每个文件的 diff
        files = []
        for fp in kept_files:
            file_diff = self.get_file_diff(commit_hash, fp)
            if file_diff:
                files.append(file_diff)

        # 估算 token 数
        content = f"{info['message']}\n" + "\n".join(f.content for f in files)
        estimated_tokens = estimate_tokens(content)

        return CommitDiff(
            commit_hash=info["hash"],
            short_hash=info["short_hash"],
            message=info["message"],
            author_name=info["author_name"],
            author_date=info["author_date"],
            files=files,
            is_truncated=is_truncated,
            total_additions=stats["insertions"],
            total_deletions=stats["deletions"],
            estimated_tokens=estimated_tokens,
        )


def format_diff_for_llm(commit_diff: CommitDiff) -> str:
    """
    将 commit diff 格式化为适合 LLM 的文本格式
    """
    lines = []

    # Commit 头部信息
    lines.append(f"Commit: {commit_diff.short_hash}")
    lines.append(f"Author: {commit_diff.author_name}")
    lines.append(f"Date: {commit_diff.author_date.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"")
    lines.append(f"    {commit_diff.message}")
    lines.append(f"")

    # 统计信息
    lines.append(f"{len(commit_diff.files)} files changed, "
                f"{commit_diff.total_additions} insertions(+), "
                f"{commit_diff.total_deletions} deletions(-)")
    lines.append(f"")

    # 文件 diff
    for file_diff in commit_diff.files:
        if file_diff.is_truncated:
            lines.append(f"diff --git a/{file_diff.path} b/{file_diff.path}")
            lines.append(f"--- (truncated)")
        else:
            lines.append(file_diff.content)
        lines.append(f"")

    return "\n".join(lines)


if __name__ == "__main__":
    print("测试 DiffBuilder...")
    print("（此模块需要真实的 git 仓库才能完整测试）")
    print("\n核心功能:")
    print("- 获取 commit 信息和统计")
    print("- 生成带截断的 diff")
    print("- 估算 token 数量")
    print("- 格式化为 LLM 可用的文本")
