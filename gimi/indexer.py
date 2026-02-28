"""
T9: 大仓库策略与断点续跑

功能：
- 在 T6 上增加分批遍历（如每批 M 个 commit）
- 每批完成后将进度与已写入的索引状态持久化
- 启动时若发现未完成的全量任务则从上一批继续
- 可配置 N/时间/分支上限
"""

import json
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Iterator, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto

from gimi.git_traversal import GitTraversal, CommitMeta
from gimi.light_index import LightIndex
from gimi.vector_index import VectorIndex
from gimi.config import LargeRepoConfig
from gimi.lock import gimi_lock


class IndexingState(Enum):
    """索引状态"""
    IDLE = auto()           # 空闲
    RUNNING = auto()       # 运行中
    PAUSED = auto()        # 暂停（可恢复）
    COMPLETED = auto()    # 完成
    FAILED = auto()        # 失败


@dataclass
class BatchProgress:
    """批次进度"""
    batch_number: int                 # 批次号
    start_commit: str                 # 起始 commit hash
    end_commit: Optional[str] = None  # 结束 commit hash
    commit_count: int = 0             # 处理的 commit 数
    started_at: Optional[str] = None  # 开始时间
    completed_at: Optional[str] = None  # 完成时间
    status: str = "pending"           # 状态: pending, running, completed, failed

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "BatchProgress":
        return cls(**data)


@dataclass
class IndexingProgress:
    """索引进度（用于断点续跑）"""
    state: str = "idle"                    # 状态
    target_branches: List[str] = field(default_factory=list)
    max_commits: Optional[int] = None
    since_date: Optional[str] = None
    batch_size: int = 100

    # 进度统计
    total_batches: int = 0
    completed_batches: int = 0
    total_commits: int = 0
    processed_commits: int = 0

    # 批次详情
    batches: List[BatchProgress] = field(default_factory=list)

    # 时间戳
    started_at: Optional[str] = None
    last_updated_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "state": self.state,
            "target_branches": self.target_branches,
            "max_commits": self.max_commits,
            "since_date": self.since_date,
            "batch_size": self.batch_size,
            "total_batches": self.total_batches,
            "completed_batches": self.completed_batches,
            "total_commits": self.total_commits,
            "processed_commits": self.processed_commits,
            "batches": [b.to_dict() for b in self.batches],
            "started_at": self.started_at,
            "last_updated_at": self.last_updated_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "IndexingProgress":
        batches = [BatchProgress.from_dict(b) for b in data.get("batches", [])]
        return cls(
            state=data.get("state", "idle"),
            target_branches=data.get("target_branches", []),
            max_commits=data.get("max_commits"),
            since_date=data.get("since_date"),
            batch_size=data.get("batch_size", 100),
            total_batches=data.get("total_batches", 0),
            completed_batches=data.get("completed_batches", 0),
            total_commits=data.get("total_commits", 0),
            processed_commits=data.get("processed_commits", 0),
            batches=batches,
            started_at=data.get("started_at"),
            last_updated_at=data.get("last_updated_at"),
            completed_at=data.get("completed_at"),
        )


class IncrementalIndexer:
    """
    增量索引器，支持分批处理和断点续跑
    """

    PROGRESS_FILENAME = "indexing_progress.json"

    def __init__(
        self,
        gimi_path: Path,
        repo_root: Path,
        config: Optional[LargeRepoConfig] = None,
    ):
        self.gimi_path = Path(gimi_path)
        self.repo_root = Path(repo_root)
        self.config = config or LargeRepoConfig()

        # 初始化组件
        self.git = GitTraversal(self.repo_root)
        self.light_index = LightIndex(self.gimi_path)
        self.vector_index = VectorIndex(self.gimi_path)

        # 进度文件路径
        self.progress_path = self.gimi_path / self.PROGRESS_FILENAME

    def _load_progress(self) -> Optional[IndexingProgress]:
        """加载进度"""
        if not self.progress_path.exists():
            return None

        try:
            data = json.loads(self.progress_path.read_text(encoding="utf-8"))
            return IndexingProgress.from_dict(data)
        except Exception:
            return None

    def _save_progress(self, progress: IndexingProgress) -> None:
        """保存进度"""
        progress.last_updated_at = datetime.now().isoformat()
        self.progress_path.write_text(
            json.dumps(progress.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _estimate_total_commits(self, branches: List[str]) -> int:
        """估算总 commit 数"""
        total = 0
        for branch in branches:
            try:
                result = self.git._run_git(
                    ["rev-list", "--count", branch],
                    check=False
                )
                if result.returncode == 0:
                    total += int(result.stdout.strip())
            except Exception:
                pass
        return total

    def _get_commits_batch(
        self,
        branch: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[CommitMeta]:
        """获取一批 commit"""
        commits = []
        for commit in self.git.get_commits(
            branch=branch,
            max_count=limit,
        ):
            # 获取文件列表和统计
            commit.files_changed = self.git.get_commit_files(commit.hash)
            commit.stats = self.git.get_commit_stats(commit.hash)
            commit.branches = [branch]
            commits.append(commit)

        return commits

    def build_index(
        self,
        branches: Optional[List[str]] = None,
        incremental: bool = True,
        progress_callback: Optional[Callable[[IndexingProgress], None]] = None,
    ) -> IndexingProgress:
        """
        构建索引（支持断点续跑）

        Args:
            branches: 要索引的分支列表，默认使用配置中的分支
            incremental: 是否尝试增量更新
            progress_callback: 进度回调函数

        Returns:
            IndexingProgress: 最终进度状态
        """
        target_branches = branches or self.config.branches

        # 检查是否有未完成的进度
        existing_progress = self._load_progress() if incremental else None

        if existing_progress and existing_progress.state in ["running", "paused"]:
            # 恢复之前的进度
            progress = existing_progress
            progress.state = "running"
        else:
            # 创建新进度
            total_commits = self._estimate_total_commits(target_branches)

            progress = IndexingProgress(
                state="running",
                target_branches=target_branches,
                max_commits=self.config.max_commits,
                batch_size=self.config.batch_size,
                total_batches=(total_commits // self.config.batch_size) + 1,
                total_commits=min(total_commits, self.config.max_commits or total_commits),
                started_at=datetime.now().isoformat(),
            )

        # 保存初始进度
        self._save_progress(progress)

        try:
            with gimi_lock(self.gimi_path):
                for branch in target_branches:
                    if progress.state == "paused":
                        break

                    skip = sum(
                        b.commit_count for b in progress.batches
                        if b.status == "completed"
                    )

                    remaining = self.config.max_commits - skip if self.config.max_commits else None
                    batch_size = self.config.batch_size

                    while True:
                        if progress.state == "paused":
                            break

                        # 获取一批 commit
                        batch_start_time = datetime.now()
                        commits = []

                        for i, commit in enumerate(self.git.get_commits(
                            branch=branch,
                            max_count=batch_size,
                        )):
                            if remaining is not None and i >= remaining:
                                break

                            # 获取文件列表和统计
                            commit.files_changed = self.git.get_commit_files(commit.hash)
                            commit.stats = self.git.get_commit_stats(commit.hash)
                            commit.branches = [branch]
                            commits.append(commit)

                        if not commits:
                            break

                        # 写入轻量索引
                        self.light_index.add_commits(commits)

                        # 写入向量索引
                        self.vector_index.add_commits(commits)

                        # 更新进度
                        batch_progress = BatchProgress(
                            batch_number=len(progress.batches) + 1,
                            start_commit=commits[0].hash,
                            end_commit=commits[-1].hash,
                            commit_count=len(commits),
                            started_at=batch_start_time.isoformat(),
                            completed_at=datetime.now().isoformat(),
                            status="completed",
                        )
                        progress.batches.append(batch_progress)
                        progress.completed_batches += 1
                        progress.processed_commits += len(commits)

                        self._save_progress(progress)

                        # 调用进度回调
                        if progress_callback:
                            progress_callback(progress)

                        # 检查是否达到最大数量
                        if remaining is not None:
                            remaining -= len(commits)
                            if remaining <= 0:
                                break

                # 保存向量索引
                self.vector_index.save()

                # 标记完成
                if progress.state != "paused":
                    progress.state = "completed"
                    progress.completed_at = datetime.now().isoformat()
                    self._save_progress(progress)

        except Exception as e:
            progress.state = "failed"
            self._save_progress(progress)
            raise

        return progress

    def resume_indexing(self) -> IndexingProgress:
        """恢复之前中断的索引任务"""
        progress = self._load_progress()

        if not progress:
            raise RuntimeError("没有找到可恢复的索引任务")

        if progress.state not in ["running", "paused"]:
            raise RuntimeError(f"当前索引任务状态为 {progress.state}，无法恢复")

        return self.build_index(
            branches=progress.target_branches,
            incremental=True,
        )

    def clear(self) -> None:
        """清空所有索引"""
        with gimi_lock(self.gimi_path):
            # 清空轻量索引
            self.light_index.clear()

            # 清空向量索引
            self._entries = {}
            self._save_index()

            # 删除进度文件
            if self.progress_path.exists():
                self.progress_path.unlink()


if __name__ == "__main__":
    import tempfile

    print("测试增量索引器...")

    with tempfile.TemporaryDirectory() as tmpdir:
        gimi_path = Path(tmpdir) / ".gimi"
        gimi_path.mkdir(parents=True)

        # 创建测试仓库根目录（模拟）
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir()

        # 创建配置
        config = LargeRepoConfig(
            max_commits=100,
            batch_size=10,
            branches=["main"],
        )

        # 创建增量索引器
        indexer = IncrementalIndexer(gimi_path, repo_root, config)
        print("增量索引器已创建")

        # 注意：由于我们没有真实的 git 仓库，无法进行完整的索引测试
        # 但我们可以测试配置和进度管理的正确性

        print("\n测试进度管理...")

        # 创建测试进度
        progress = IndexingProgress(
            state="running",
            target_branches=["main", "develop"],
            batch_size=50,
            total_batches=10,
            total_commits=500,
            started_at=datetime.now().isoformat(),
        )

        # 添加一些批次进度
        for i in range(3):
            batch = BatchProgress(
                batch_number=i + 1,
                start_commit=f"commit{i}abc",
                end_commit=f"commit{i}xyz",
                commit_count=50,
                status="completed",
            )
            progress.batches.append(batch)
            progress.completed_batches += 1
            progress.processed_commits += 50

        # 保存进度
        indexer._save_progress(progress)
        print(f"进度已保存: {indexer.progress_path}")

        # 加载进度
        loaded_progress = indexer._load_progress()
        print(f"\n加载的进度:")
        print(f"  状态: {loaded_progress.state}")
        print(f"  目标分支: {loaded_progress.target_branches}")
        print(f"  已完成批次: {loaded_progress.completed_batches}/{loaded_progress.total_batches}")
        print(f"  已处理 commit: {loaded_progress.processed_commits}/{loaded_progress.total_commits}")

        # 测试轻量索引和向量索引的基本功能
        print("\n\n测试轻量索引和向量索引...")

        # 创建一些测试 commit
        from gimi.git_traversal import CommitMeta
        from datetime import datetime

        test_commits = [
            CommitMeta(
                hash=f"test{i:03d}abc{"x" * 33}",
                short_hash=f"test{i:03d}a",
                message=f"Test commit {i} with some keywords",
                author_name="Test User",
                author_email="test@example.com",
                author_date=datetime.now(),
                committer_name="Test User",
                committer_email="test@example.com",
                committer_date=datetime.now(),
                branches=["main"],
                parents=[],
                files_changed=[f"src/file{i}.py"],
                stats={"insertions": 10, "deletions": 5, "files_changed": 1},
            )
            for i in range(5)
        ]

        # 添加到轻量索引
        indexer.light_index.add_commits(test_commits)
        print(f"已添加 {len(test_commits)} 个 commit 到轻量索引")
        print(f"  索引中 commit 数: {indexer.light_index.get_commit_count()}")

        # 添加到向量索引
        indexer.vector_index.add_commits(test_commits)
        indexer.vector_index.save()
        print(f"\n已添加 {len(test_commits)} 个 commit 到向量索引")
        print(f"  索引条目数: {indexer.vector_index.get_entry_count()}")

        # 测试向量搜索
        print("\n测试向量搜索 'keywords':")
        results = indexer.vector_index.search("keywords", top_k=3)
        for commit_hash, similarity in results:
            print(f"  - {commit_hash[:8]} (相似度: {similarity:.4f})")

    print("\n所有测试完成!")
