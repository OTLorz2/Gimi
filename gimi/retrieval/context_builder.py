"""
上下文构建器
负责获取commit diff并构建LLM上下文
"""

import subprocess
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict

from gimi.indexing.git_collector import CommitMetadata


@dataclass
class FileDiff:
    """单个文件的diff信息"""

    path: str
    old_path: Optional[str]  # 重命名时使用
    status: str  # added, modified, deleted, renamed
    diff_content: str
    added_lines: int
    removed_lines: int

    def truncate(self, max_lines: int) -> "FileDiff":
        """截断diff内容"""
        if max_lines <= 0:
            return self

        lines = self.diff_content.split("\n")
        if len(lines) <= max_lines:
            return self

        # 保留文件头和部分diff
        truncated = "\n".join(lines[:max_lines])
        truncated += f"\n... ({len(lines) - max_lines} more lines)"

        return FileDiff(
            path=self.path,
            old_path=self.old_path,
            status=self.status,
            diff_content=truncated,
            added_lines=self.added_lines,
            removed_lines=self.removed_lines,
        )


@dataclass
class CommitDiff:
    """Commit的完整diff信息"""

    commit: CommitMetadata
    file_diffs: List[FileDiff]
    total_additions: int
    total_deletions: int

    def truncate(
        self,
        max_files: int = 10,
        max_lines_per_file: int = 50,
    ) -> "CommitDiff":
        """截断diff内容"""
        # 限制文件数量
        truncated_files = self.file_diffs[:max_files]

        # 截断每个文件的diff
        truncated_files = [f.truncate(max_lines_per_file) for f in truncated_files]

        # 计算新的统计
        total_additions = sum(f.added_lines for f in truncated_files)
        total_deletions = sum(f.removed_lines for f in truncated_files)

        return CommitDiff(
            commit=self.commit,
            file_diffs=truncated_files,
            total_additions=total_additions,
            total_deletions=total_deletions,
        )


class ContextBuilder:
    """
    上下文构建器

    负责:
    1. 获取commit的diff
    2. 解析diff内容
    3. 构建LLM可用的上下文
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def _run_git_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """执行git命令"""
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=True,
            )
            return result
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git命令执行失败: {e.stderr}")

    def get_commit_diff(self, commit_hash: str) -> str:
        """
        获取commit的原始diff

        Args:
            commit_hash: commit hash

        Returns:
            diff文本
        """
        result = self._run_git_command(["show", commit_hash])
        return result.stdout

    def parse_diff(self, diff_text: str) -> List[FileDiff]:
        """
        解析diff文本

        Args:
            diff_text: 原始diff文本

        Returns:
            FileDiff列表
        """
        file_diffs = []

        # 分割每个文件的diff
        # 格式: diff --git a/file b/file
        file_sections = re.split(r"(?=diff --git )", diff_text)

        for section in file_sections:
            if not section.strip() or "diff --git" not in section:
                continue

            # 解析文件路径
            file_match = re.search(r"diff --git a/(.+?) b/(.+?)(?:\n|$)", section)
            if not file_match:
                continue

            old_path = file_match.group(1)
            new_path = file_match.group(2)

            # 判断文件状态
            status = "modified"
            if old_path == "/dev/null":
                status = "added"
                old_path = None
            elif new_path == "/dev/null":
                status = "deleted"
            elif old_path != new_path:
                status = "renamed"

            # 提取diff内容（@@行开始的部分）
            diff_content = ""
            diff_match = re.search(r"(@@.+)$", section, re.DOTALL)
            if diff_match:
                diff_content = diff_match.group(1).strip()

            # 计算增删行数
            added_lines = len(re.findall(r"^\+[^+]", diff_content, re.MULTILINE))
            removed_lines = len(re.findall(r"^-[^-]", diff_content, re.MULTILINE))

            file_diff = FileDiff(
                path=new_path if new_path != "/dev/null" else old_path,
                old_path=old_path if old_path != new_path else None,
                status=status,
                diff_content=diff_content,
                added_lines=added_lines,
                removed_lines=removed_lines,
            )

            file_diffs.append(file_diff)

        return file_diffs

    def get_commit_diff_structured(self, commit_hash: str) -> CommitDiff:
        """
        获取结构化的commit diff

        Args:
            commit_hash: commit hash

        Returns:
            CommitDiff对象
        """
        from gimi.indexing.git_collector import GitCollector

        # 获取commit元数据
        collector = GitCollector(self.repo_root)
        commit = collector.get_commit_metadata(commit_hash)

        if not commit:
            raise ValueError(f"Commit not found: {commit_hash}")

        # 获取并解析diff
        diff_text = self.get_commit_diff(commit_hash)
        file_diffs = self.parse_diff(diff_text)

        # 计算总计
        total_additions = sum(f.added_lines for f in file_diffs)
        total_deletions = sum(f.removed_lines for f in file_diffs)

        return CommitDiff(
            commit=commit,
            file_diffs=file_diffs,
            total_additions=total_additions,
            total_deletions=total_deletions,
        )

    def build_context(
        self,
        commits: List[CommitMetadata],
        max_files_per_commit: int = 10,
        max_lines_per_file: int = 50,
        max_total_commits: int = 10,
    ) -> List[CommitDiff]:
        """
        为多个commit构建上下文

        Args:
            commits: commit列表
            max_files_per_commit: 每个commit最多包含的文件数
            max_lines_per_file: 每个文件最多包含的行数
            max_total_commits: 最多处理多少个commit

        Returns:
            CommitDiff列表
        """
        context = []

        for commit in commits[:max_total_commits]:
            try:
                commit_diff = self.get_commit_diff_structured(commit.hash)
                truncated = commit_diff.truncate(
                    max_files=max_files_per_commit,
                    max_lines_per_file=max_lines_per_file,
                )
                context.append(truncated)
            except Exception as e:
                # 忽略无法获取diff的commit
                continue

        return context

    def format_context_for_llm(
        self,
        commit_diffs: List[CommitDiff],
        include_stats: bool = True,
    ) -> str:
        """
        将上下文格式化为LLM可用的文本

        Args:
            commit_diffs: CommitDiff列表
            include_stats: 是否包含统计信息

        Returns:
            格式化后的文本
        """
        sections = []

        for i, diff in enumerate(commit_diffs, 1):
            commit = diff.commit

            section = f"## [{i}] Commit: {commit.short_hash}\n"
            section += f"Author: {commit.author} <{commit.author_email}>\n"
            section += f"Date: {commit.datetime.isoformat()}\n"
            section += f"Message: {commit.message}\n"

            if include_stats:
                section += f"\nStats: +{diff.total_additions}/-{diff.total_deletions} in {len(diff.file_diffs)} files\n"

            # 添加文件diff
            for file_diff in diff.file_diffs:
                section += f"\n### {file_diff.path}\n"
                section += f"```diff\n{file_diff.diff_content}\n```\n"

            sections.append(section)

        return "\n\n---\n\n".join(sections)


class PromptBuilder:
    """
    Prompt构建器

    负责构建发送给LLM的prompt
    """

    SYSTEM_PROMPT_TEMPLATE = """你是一个专业的代码审查助手，擅长分析git历史并提供代码建议。

你的任务是根据用户的问题和提供的git commit历史，给出有价值的代码建议、解释或最佳实践。

请遵循以下原则：
1. 基于提供的commit历史进行分析，不要编造信息
2. 给出具体、可操作的建议
3. 如果历史记录不足以回答问题，请明确说明
4. 引用相关的commit hash作为参考

输出格式：
- 首先给出简要回答
- 然后提供详细分析和依据
- 最后列出参考的commit"""

    def __init__(self, user_query: str, context: str):
        self.user_query = user_query
        self.context = context

    def build_messages(self) -> List[Dict[str, str]]:
        """构建消息列表"""
        return [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT_TEMPLATE,
            },
            {
                "role": "user",
                "content": self._build_user_message(),
            },
        ]

    def _build_user_message(self) -> str:
        """构建用户消息"""
        return f"""## 问题

{self.user_query}

## 相关Git历史

{self.context}

请基于以上git历史，回答我的问题。"""

    @staticmethod
    def format_response(response: str, referenced_commits: List[str]) -> str:
        """格式化最终响应"""
        output = response + "\n\n"
        output += "---\n"
        output += "**参考Commit**: " + ", ".join(referenced_commits[:5])
        if len(referenced_commits) > 5:
            output += f" 等{len(referenced_commits)}个commit"
        return output
