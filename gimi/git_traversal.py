"""
T6: Git 遍历与 commit 元数据

功能：
- 从 repo root 遍历指定分支的 commit
- 产出结构化数据：hash、message、分支、改动文件路径列表、时间
- 不在此步拉取完整 diff，只做元数据
- 受大仓库配置约束（N条/时间/分支）
"""

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Set, Iterator, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommitMeta:
    """Commit 元数据结构"""
    hash: str                          # 完整 commit hash
    short_hash: str                    # 短 hash
    message: str                       # commit message
    author_name: str                   # 作者名
    author_email: str                # 作者邮箱
    author_date: datetime              # 作者时间
    committer_name: str                # 提交者名
    committer_email: str               # 提交者邮箱
    committer_date: datetime           # 提交时间
    branches: List[str] = field(default_factory=list)  # 所属分支列表
    parents: List[str] = field(default_factory=list)   # 父 commit hash 列表
    files_changed: List[str] = field(default_factory=list)  # 改动的文件路径
    stats: Dict[str, int] = field(default_factory=dict)     # 统计信息

    def __post_init__(self):
        """初始化后处理"""
        if not self.short_hash and self.hash:
            self.short_hash = self.hash[:7]

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "hash": self.hash,
            "short_hash": self.short_hash,
            "message": self.message,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_date": self.author_date.isoformat() if self.author_date else None,
            "committer_name": self.committer_name,
            "committer_email": self.committer_email,
            "committer_date": self.committer_date.isoformat() if self.committer_date else None,
            "branches": self.branches,
            "parents": self.parents,
            "files_changed": self.files_changed,
            "stats": self.stats,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CommitMeta":
        """从字典创建"""
        return cls(
            hash=data.get("hash", ""),
            short_hash=data.get("short_hash", ""),
            message=data.get("message", ""),
            author_name=data.get("author_name", ""),
            author_email=data.get("author_email", ""),
            author_date=datetime.fromisoformat(data["author_date"]) if data.get("author_date") else None,
            committer_name=data.get("committer_name", ""),
            committer_email=data.get("committer_email", ""),
            committer_date=datetime.fromisoformat(data["committer_date"]) if data.get("committer_date") else None,
            branches=data.get("branches", []),
            parents=data.get("parents", []),
            files_changed=data.get("files_changed", []),
            stats=data.get("stats", {}),
        )


class GitTraversal:
    """Git 遍历器，用于枚举 commit 并提取元数据"""

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def _run_git(
        self,
        args: List[str],
        check: bool = True,
        capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """运行 git 命令"""
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            cwd=self.repo_root,
            capture_output=capture_output,
            text=True,
            check=False,
        )

        if check and result.returncode != 0:
            raise RuntimeError(f"Git 命令失败: {' '.join(cmd)}\n{result.stderr}")

        return result

    def parse_commit_from_log(
        self,
        log_output: str,
        format_pattern: Optional[str] = None
    ) -> CommitMeta:
        """
        从 git log 输出解析 commit 元数据

        使用特殊格式：hash、author、date 等用分隔符分隔
        """
        lines = log_output.strip().split("\n")
        if not lines:
            raise ValueError("空的 log 输出")

        # 解析第一行的基本信息
        # 格式: hash<SEP>author_name<SEP>author_email<SEP>author_date<SEP>subject
        SEP = "\x00"  # 使用空字符作为分隔符

        # 使用 git log --format 的自定义格式解析
        parts = lines[0].split(SEP)

        commit_hash = parts[0] if len(parts) > 0 else ""
        author_name = parts[1] if len(parts) > 1 else ""
        author_email = parts[2] if len(parts) > 2 else ""
        author_date_str = parts[3] if len(parts) > 3 else ""
        message = parts[4] if len(parts) > 4 else ""

        # 解析日期
        try:
            author_date = datetime.fromtimestamp(int(author_date_str)) if author_date_str else None
        except ValueError:
            author_date = None

        # 剩余行是完整 message 或文件列表
        full_message = message
        if len(lines) > 1:
            # 检查是否是文件列表（以某种前缀开头）
            full_message = "\n".join(lines)

        return CommitMeta(
            hash=commit_hash,
            short_hash=commit_hash[:7] if commit_hash else "",
            message=full_message.strip(),
            author_name=author_name,
            author_email=author_email,
            author_date=author_date,
            committer_name=author_name,  # 简化处理
            committer_email=author_email,
            committer_date=author_date,
        )

    def get_commits(
        self,
        branch: Optional[str] = None,
        max_count: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        author: Optional[str] = None,
        grep: Optional[str] = None,
        file_paths: Optional[List[str]] = None,
    ) -> Iterator[CommitMeta]:
        """
        获取 commit 列表

        Args:
            branch: 分支名，默认为当前分支
            max_count: 最大返回数量
            since: 起始时间（如 "2024-01-01" 或 "1 week ago"）
            until: 结束时间
            author: 作者过滤
            grep: message 关键词过滤
            file_paths: 文件路径过滤

        Yields:
            CommitMeta: commit 元数据
        """
        # 构建 git log 命令
        args = ["log"]

        # 格式：使用占位符分隔的格式
        # %H: commit hash
        # %an: author name
        # %ae: author email
        # %at: author date (timestamp)
        # %s: subject
        format_str = "%H%x00%an%x00%ae%x00%at%x00%s"
        args.extend(["--format=" + format_str])

        # 添加过滤条件
        if max_count:
            args.extend(["--max-count", str(max_count)])

        if since:
            args.extend(["--since", since])

        if until:
            args.extend(["--until", until])

        if author:
            args.extend(["--author", author])

        if grep:
            args.extend(["--grep", grep])

        # 文件路径过滤（放在最后）
        if file_paths:
            args.append("--")
            args.extend(file_paths)
        else:
            args.append("--")

        # 指定分支
        if branch:
            args.insert(1, branch)

        # 执行命令
        result = self._run_git(args, check=False)

        if result.returncode != 0 or not result.stdout.strip():
            return

        # 解析输出
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue

            try:
                meta = self._parse_log_line(line)
                if meta:
                    yield meta
            except Exception as e:
                # 解析失败时跳过
                continue

    def _parse_log_line(self, line: str) -> Optional[CommitMeta]:
        """解析一行 git log 输出"""
        parts = line.split("\x00")

        if len(parts) < 5:
            return None

        commit_hash = parts[0]
        author_name = parts[1]
        author_email = parts[2]
        author_date_str = parts[3]
        message = parts[4]

        # 解析日期
        try:
            author_date = datetime.fromtimestamp(int(author_date_str))
        except (ValueError, TypeError):
            author_date = None

        return CommitMeta(
            hash=commit_hash,
            short_hash=commit_hash[:7] if commit_hash else "",
            message=message,
            author_name=author_name,
            author_email=author_email,
            author_date=author_date,
            committer_name=author_name,
            committer_email=author_email,
            committer_date=author_date,
        )

    def get_commit_files(self, commit_hash: str) -> List[str]:
        """
        获取 commit 改动的文件列表

        Args:
            commit_hash: commit hash

        Returns:
            List[str]: 文件路径列表
        """
        result = self._run_git(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            check=False
        )

        if result.returncode != 0:
            return []

        return [f for f in result.stdout.strip().split("\n") if f]

    def get_commit_stats(self, commit_hash: str) -> dict:
        """
        获取 commit 的统计信息

        Args:
            commit_hash: commit hash

        Returns:
            dict: 统计信息（insertions, deletions, files_changed）
        """
        result = self._run_git(
            ["show", "--stat", "--format=", commit_hash],
            check=False
        )

        stats = {"insertions": 0, "deletions": 0, "files_changed": 0}

        if result.returncode != 0 or not result.stdout:
            return stats

        # 解析统计信息
        lines = result.stdout.strip().split("\n")
        for line in lines:
            # 匹配类似 "5 files changed, 100 insertions(+), 20 deletions(-)"
            if "files changed" in line or "file changed" in line:
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


if __name__ == "__main__":
    import tempfile

    print("测试 Git 遍历...")

    try:
        resolver = RepoResolver()
        repo_root = resolver.resolve_repo_root()
        print(f"仓库根目录: {repo_root}")

        traversal = GitTraversal(repo_root)

        # 测试 1: 获取最近的 commit
        print("\n测试 1: 获取最近 5 个 commit")
        commits = list(traversal.get_commits(max_count=5))
        print(f"  获取到 {len(commits)} 个 commit")

        for commit in commits:
            print(f"  - {commit.short_hash}: {commit.message[:50]}...")

        if commits:
            # 测试 2: 获取 commit 的文件列表
            print(f"\n测试 2: 获取 commit {commits[0].short_hash} 的文件列表")
            files = traversal.get_commit_files(commits[0].hash)
            print(f"  改动了 {len(files)} 个文件")
            for f in files[:5]:  # 只显示前 5 个
                print(f"    - {f}")
            if len(files) > 5:
                print(f"    ... 还有 {len(files) - 5} 个文件")

            # 测试 3: 获取 commit 统计
            print(f"\n测试 3: 获取 commit {commits[0].short_hash} 的统计")
            stats = traversal.get_commit_stats(commits[0].hash)
            print(f"  文件变更: {stats['files_changed']}")
            print(f"  插入: {stats['insertions']}")
            print(f"  删除: {stats['deletions']}")

        # 测试 4: 按文件过滤
        print("\n测试 4: 按文件路径过滤")
        # 使用当前存在的文件路径
        file_commits = list(traversal.get_commits(
            max_count=10,
            file_paths=["gimi/repo.py"]  # 使用已存在的文件
        ))
        print(f"  涉及 gimi/repo.py 的最近 commit: {len(file_commits)} 个")
        for c in file_commits[:3]:
            print(f"    - {c.short_hash}: {c.message[:40]}...")

    except RuntimeError as e:
        print(f"错误: {e}")
        print("请在 git 仓库中运行此测试")
    except Exception as e:
        print(f"测试出错: {e}")
        import traceback
        traceback.print_exc()
