"""
Git遍历与commit元数据收集
"""

import subprocess
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Iterator, Dict, Set, Callable


@dataclass
class CommitMetadata:
    """Commit元数据结构"""

    hash: str
    message: str
    author: str
    author_email: str
    timestamp: int  # Unix timestamp
    parent_hashes: List[str] = field(default_factory=list)
    changed_files: List[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    branch: str = ""

    @property
    def short_hash(self) -> str:
        """返回短hash"""
        return self.hash[:8]

    @property
    def datetime(self) -> datetime:
        """返回datetime对象"""
        return datetime.fromtimestamp(self.timestamp)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "hash": self.hash,
            "short_hash": self.short_hash,
            "message": self.message,
            "author": self.author,
            "author_email": self.author_email,
            "timestamp": self.timestamp,
            "datetime": self.datetime.isoformat(),
            "parent_hashes": self.parent_hashes,
            "changed_files": self.changed_files,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "branch": self.branch,
        }


class GitCollector:
    """
    Git commit元数据收集器

    负责遍历git历史，收集commit的元数据（不包含完整diff）
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self._commit_cache: Dict[str, CommitMetadata] = {}

    def _run_git_command(
        self, args: List[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        """执行git命令"""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=check,
            )
            return result
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git命令执行失败: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("未找到git命令")

    def get_current_branch(self) -> str:
        """获取当前分支名"""
        result = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def get_all_branches(self) -> List[str]:
        """获取所有本地分支列表"""
        result = self._run_git_command(["branch", "--format=%(refname:short)"])
        return [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]

    def _parse_commit_from_log(self, log_line: str, branch: str = "") -> Optional[CommitMetadata]:
        """
        从格式化log行解析commit

        格式: hash|parent_hashes|author|author_email|timestamp|subject
        """
        parts = log_line.split("|", 5)
        if len(parts) < 6:
            return None

        try:
            commit_hash = parts[0]
            parent_hashes = [p for p in parts[1].split() if p]
            author = parts[2]
            author_email = parts[3]
            timestamp = int(parts[4])
            message = parts[5]

            return CommitMetadata(
                hash=commit_hash,
                message=message,
                author=author,
                author_email=author_email,
                timestamp=timestamp,
                parent_hashes=parent_hashes,
                branch=branch,
            )
        except (ValueError, IndexError) as e:
            # 解析失败，跳过
            return None

    def get_commit_metadata(self, commit_hash: str) -> Optional[CommitMetadata]:
        """获取单个commit的元数据"""
        if commit_hash in self._commit_cache:
            return self._commit_cache[commit_hash]

        # 使用git show获取单个commit信息
        format_str = "%H|%P|%an|%ae|%at|%s"
        result = self._run_git_command(
            ["show", "--no-patch", f"--format={format_str}", commit_hash],
            check=False,
        )

        if result.returncode != 0:
            return None

        commit = self._parse_commit_from_log(result.stdout.strip())
        if commit:
            self._commit_cache[commit_hash] = commit
        return commit

    def get_commit_changed_files(self, commit_hash: str) -> List[str]:
        """获取commit改动的文件列表"""
        result = self._run_git_command(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            check=False,
        )

        if result.returncode != 0:
            return []

        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
        return files

    def get_commit_stats(self, commit_hash: str) -> tuple:
        """获取commit的增删行数统计"""
        result = self._run_git_command(
            ["show", "--format="", "--stat", commit_hash],
            check=False,
        )

        if result.returncode != 0:
            return 0, 0

        # 解析stat输出中的数字
        # 格式示例: " 5 files changed, 100 insertions(+), 20 deletions(-)"
        output = result.stdout.strip()
        insertions = 0
        deletions = 0

        import re

        # 匹配插入数
        match = re.search(r"(\d+) insertion", output)
        if match:
            insertions = int(match.group(1))

        # 匹配删除数
        match = re.search(r"(\d+) deletion", output)
        if match:
            deletions = int(match.group(1))

        return insertions, deletions

    def iter_commits(
        self,
        branch: Optional[str] = None,
        since: Optional[str] = None,
        max_count: Optional[int] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> Iterator[CommitMetadata]:
        """
        遍历commit

        Args:
            branch: 分支名,None表示当前分支
            since: 起始日期(YYYY-MM-DD格式)
            max_count: 最大返回数量
            progress_callback: 进度回调函数(current, total)

        Yields:
            CommitMetadata对象
        """
        # 构建git log命令
        cmd = ["log", "--format=%H|%P|%an|%ae|%at|%s"]

        if since:
            cmd.extend(["--since", since])

        if max_count:
            cmd.extend(["--max-count", str(max_count)])

        # 分支参数放在最后
        if branch:
            cmd.append(branch)

        # 执行命令
        result = self._run_git_command(cmd)

        lines = result.stdout.strip().split("\n")
        total = len(lines) if max_count is None else min(len(lines), max_count)
        current = 0

        branch_name = branch or self.get_current_branch()

        for line in lines:
            if not line.strip():
                continue

            commit = self._parse_commit_from_log(line.strip(), branch=branch_name)
            if commit:
                # 补充统计信息
                commit.changed_files = self.get_commit_changed_files(commit.hash)
                commit.insertions, commit.deletions = self.get_commit_stats(commit.hash)

                current += 1
                if progress_callback:
                    progress_callback(current, total if max_count else None)

                yield commit

                # 检查是否达到最大数量
                if max_count and current >= max_count:
                    break

    def get_commit_count(
        self,
        branch: Optional[str] = None,
        since: Optional[str] = None,
    ) -> int:
        """获取commit总数"""
        cmd = ["rev-list", "--count", "HEAD"]

        if since:
            cmd.extend(["--since", since])

        if branch:
            cmd[2] = branch

        result = self._run_git_command(cmd, check=False)

        if result.returncode != 0:
            return 0

        try:
            return int(result.stdout.strip())
        except ValueError:
            return 0
