"""
T4: 配置加载与 refs 快照格式

功能：
- 从 `.gimi/config.json` 读取非敏感配置（模型、K、截断规则、大仓库上限等）
- 定义并持久化「refs 快照」格式（如各分支 HEAD hash）
- 在索引构建/更新完成后写快照
- 首次运行无配置时使用默认值或引导生成
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class ModelConfig:
    """模型配置"""
    provider: str = "openai"           # LLM 提供商
    model: str = "gpt-3.5-turbo"      # 模型名称
    api_key: Optional[str] = None     # API key（不持久化到 config.json）
    base_url: Optional[str] = None    # 自定义 API base URL
    temperature: float = 0.7            # 温度参数
    max_tokens: int = 2000            # 最大 token 数


@dataclass
class RetrievalConfig:
    """检索配置"""
    top_k: int = 15                   # 检索返回的 commit 数量
    candidate_factor: int = 5         # 候选集倍数（如 top_k=15, factor=5 -> 候选 75）
    keyword_weight: float = 0.3     # 关键词检索权重
    path_weight: float = 0.2        # 路径匹配权重
    semantic_weight: float = 0.5    # 语义检索权重
    enable_rerank: bool = False     # 是否启用二阶段重排
    rerank_top_n: int = 10          # 重排后保留的数量


@dataclass
class TruncateConfig:
    """截断配置"""
    max_files_per_commit: int = 10    # 每个 commit 最多保留文件数
    max_lines_per_file: int = 100   # 每个文件最多保留行数
    max_diff_tokens: int = 4000     # diff 最大 token 数（估算）
    max_total_tokens: int = 8000    # 总上下文最大 token 数


@dataclass
class LargeRepoConfig:
    """大仓库配置"""
    max_commits: Optional[int] = 10000     # 最大索引 commit 数
    max_age_days: Optional[int] = 365    # 只索引最近 N 天的 commit
    branches: List[str] = field(default_factory=lambda: ["main", "master"])  # 要索引的分支
    batch_size: int = 100                # 每批处理的 commit 数量


@dataclass
class GimiConfig:
    """Gimi 完整配置"""
    version: str = "0.1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    model: ModelConfig = field(default_factory=ModelConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    truncate: TruncateConfig = field(default_factory=TruncateConfig)
    large_repo: LargeRepoConfig = field(default_factory=LargeRepoConfig)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（排除敏感信息）"""
        data = asdict(self)
        # 确保 API key 不被序列化
        if "model" in data and "api_key" in data["model"]:
            data["model"]["api_key"] = None
        return data

    def save(self, config_path: Path) -> None:
        """保存配置到文件"""
        self.updated_at = datetime.now().isoformat()
        config_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def load(cls, config_path: Path) -> "GimiConfig":
        """从文件加载配置"""
        if not config_path.exists():
            return cls()

        data = json.loads(config_path.read_text(encoding="utf-8"))
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "GimiConfig":
        """从字典创建配置对象"""
        config = cls(
            version=data.get("version", "0.1.0"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

        if "model" in data:
            config.model = ModelConfig(**data["model"])
        if "retrieval" in data:
            config.retrieval = RetrievalConfig(**data["retrieval"])
        if "truncate" in data:
            config.truncate = TruncateConfig(**data["truncate"])
        if "large_repo" in data:
            config.large_repo = LargeRepoConfig(**data["large_repo"])

        return config


# =============================================================================
# Refs 快照管理
# =============================================================================

@dataclass
class RefsSnapshot:
    """
    Git refs 快照

    用于记录索引构建时的仓库状态，以便后续检测索引是否过期。
    """
    branches: Dict[str, str]  # 分支名 -> HEAD commit hash
    tags: Dict[str, str]      # 标签名 -> commit hash
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "branches": self.branches,
            "tags": self.tags,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RefsSnapshot":
        """从字典创建"""
        return cls(
            branches=data.get("branches", {}),
            tags=data.get("tags", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )

    def save(self, path: Path) -> None:
        """保存到文件"""
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> Optional["RefsSnapshot"]:
        """从文件加载"""
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(data)


def capture_refs_snapshot(repo_root: Path) -> RefsSnapshot:
    """
    捕获当前仓库的 refs 快照

    Args:
        repo_root: 仓库根目录

    Returns:
        RefsSnapshot: refs 快照
    """
    import subprocess

    branches = {}
    tags = {}

    # 获取所有分支的 HEAD
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads/"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    branches[parts[0]] = parts[1]
    except subprocess.CalledProcessError:
        pass

    # 获取所有标签
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/tags/"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    tags[parts[0]] = parts[1]
    except subprocess.CalledProcessError:
        pass

    return RefsSnapshot(branches=branches, tags=tags)


def get_config_path(gimi_path: Path) -> Path:
    """获取配置文件路径"""
    return gimi_path / "config.json"


def get_refs_snapshot_path(gimi_path: Path) -> Path:
    """获取 refs 快照文件路径"""
    return gimi_path / "refs_snapshot.json"


if __name__ == "__main__":
    import tempfile

    # 测试配置管理
    print("测试配置管理...")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"

        # 创建默认配置
        config = GimiConfig()
        print(f"默认模型: {config.model.model}")
        print(f"默认 top_k: {config.retrieval.top_k}")

        # 修改配置
        config.model.model = "gpt-4"
        config.retrieval.top_k = 20

        # 保存配置
        config.save(config_path)
        print(f"\n配置已保存到: {config_path}")
        print(config_path.read_text())

        # 加载配置
        loaded_config = GimiConfig.load(config_path)
        print(f"\n加载的模型: {loaded_config.model.model}")
        print(f"加载的 top_k: {loaded_config.retrieval.top_k}")

    # 测试 refs 快照
    print("\n\n测试 refs 快照...")

    try:
        resolver = RepoResolver()
        repo_root = resolver.resolve_repo_root()

        snapshot = capture_refs_snapshot(repo_root)
        print(f"捕获到 {len(snapshot.branches)} 个分支")
        print(f"捕获到 {len(snapshot.tags)} 个标签")
        print(f"时间戳: {snapshot.timestamp}")

        # 保存和加载
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "refs_snapshot.json"
            snapshot.save(snapshot_path)
            print(f"\n快照已保存到: {snapshot_path}")

            loaded = RefsSnapshot.load(snapshot_path)
            print(f"加载的分支数: {len(loaded.branches)}")

    except RuntimeError as e:
        print(f"跳过测试（不在 git 仓库中）: {e}")

    print("\n所有测试完成!")
