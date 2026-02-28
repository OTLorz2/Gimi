"""
T5: 索引有效性校验

功能：
- 启动时读取当前仓库 refs，与 `.gimi` 内 refs 快照比对
- 若不一致则标记索引过期并决定：提示用户重建或自动触发增量/全量
- 触发逻辑可先简化为「需要重建」标志，由后续索引任务消费
"""

import json
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum, auto

from gimi.config import RefsSnapshot, capture_refs_snapshot, get_refs_snapshot_path
from gimi.repo import RepoResolver


class IndexStatus(Enum):
    """索引状态枚举"""
    VALID = auto()        # 索引有效，可以使用
    STALE = auto()       # 索引过期，需要重建
    MISSING = auto()     # 索引不存在，需要创建
    CORRUPTED = auto()   # 索引损坏，需要重建


@dataclass
class IndexHealth:
    """索引健康检查结果"""
    status: IndexStatus
    message: str
    snapshot_diff: Optional[dict] = None  # 差异详情

    def is_usable(self) -> bool:
        """索引是否可用"""
        return self.status == IndexStatus.VALID


def check_index_exists(gimi_path: Path) -> bool:
    """
    检查索引是否存在

    Args:
        gimi_path: .gimi 目录路径

    Returns:
        bool: 索引是否存在
    """
    index_dir = gimi_path / "index"
    vectors_dir = gimi_path / "vectors"

    # 检查是否有索引文件
    has_index = index_dir.exists() and any(index_dir.iterdir())
    has_vectors = vectors_dir.exists() and any(vectors_dir.iterdir())

    return has_index or has_vectors


def load_stored_snapshot(gimi_path: Path) -> Optional[RefsSnapshot]:
    """
    加载存储的 refs 快照

    Args:
        gimi_path: .gimi 目录路径

    Returns:
        Optional[RefsSnapshot]: 快照对象，如果不存在则返回 None
    """
    snapshot_path = get_refs_snapshot_path(gimi_path)
    return RefsSnapshot.load(snapshot_path)


def compare_refs(
    current: RefsSnapshot,
    stored: RefsSnapshot
) -> Tuple[bool, dict]:
    """
    比较两个 refs 快照

    Args:
        current: 当前仓库的快照
        stored: 存储的快照

    Returns:
        Tuple[bool, dict]: (是否一致, 差异详情)
    """
    differences = {
        "added_branches": [],
        "removed_branches": [],
        "modified_branches": [],
        "added_tags": [],
        "removed_tags": [],
        "modified_tags": [],
    }

    # 比较分支
    current_branches = set(current.branches.keys())
    stored_branches = set(stored.branches.keys())

    differences["added_branches"] = list(current_branches - stored_branches)
    differences["removed_branches"] = list(stored_branches - current_branches)

    for branch in current_branches & stored_branches:
        if current.branches[branch] != stored.branches[branch]:
            differences["modified_branches"].append({
                "name": branch,
                "old": stored.branches[branch][:8],
                "new": current.branches[branch][:8],
            })

    # 比较标签
    current_tags = set(current.tags.keys())
    stored_tags = set(stored.tags.keys())

    differences["added_tags"] = list(current_tags - stored_tags)
    differences["removed_tags"] = list(stored_tags - current_tags)

    for tag in current_tags & stored_tags:
        if current.tags[tag] != stored.tags[tag]:
            differences["modified_tags"].append({
                "name": tag,
                "old": stored.tags[tag][:8],
                "new": current.tags[tag][:8],
            })

    # 判断是否一致
    is_consistent = (
        not differences["added_branches"]
        and not differences["removed_branches"]
        and not differences["modified_branches"]
        and not differences["added_tags"]
        and not differences["removed_tags"]
        and not differences["modified_tags"]
    )

    return is_consistent, differences


def check_index_health(gimi_path: Path) -> IndexHealth:
    """
    检查索引健康状态

    Args:
        gimi_path: .gimi 目录路径

    Returns:
        IndexHealth: 健康检查结果
    """
    # 1. 检查索引是否存在
    if not check_index_exists(gimi_path):
        return IndexHealth(
            status=IndexStatus.MISSING,
            message="索引不存在，需要创建。"
        )

    # 2. 加载存储的 refs 快照
    stored_snapshot = load_stored_snapshot(gimi_path)
    if stored_snapshot is None:
        return IndexHealth(
            status=IndexStatus.CORRUPTED,
            message="无法加载 refs 快照，索引可能已损坏。"
        )

    # 3. 捕获当前仓库的 refs 快照
    try:
        resolver = RepoResolver()
        repo_root = resolver.resolve_repo_root()
        current_snapshot = capture_refs_snapshot(repo_root)
    except Exception as e:
        return IndexHealth(
            status=IndexStatus.CORRUPTED,
            message=f"无法捕获当前 refs 快照: {e}"
        )

    # 4. 比较 refs 快照
    is_consistent, differences = compare_refs(current_snapshot, stored_snapshot)

    if is_consistent:
        return IndexHealth(
            status=IndexStatus.VALID,
            message="索引有效，可以使用。",
            snapshot_diff=differences
        )
    else:
        # 构建差异描述
        diff_parts = []
        if differences["modified_branches"]:
            branch_names = [d["name"] for d in differences["modified_branches"]]
            diff_parts.append(f"分支更新: {', '.join(branch_names)}")
        if differences["added_branches"]:
            diff_parts.append(f"新增分支: {', '.join(differences['added_branches'])}")
        if differences["removed_branches"]:
            diff_parts.append(f"删除分支: {', '.join(differences['removed_branches'])}")

        diff_desc = "; ".join(diff_parts) if diff_parts else "refs 发生变更"

        return IndexHealth(
            status=IndexStatus.STALE,
            message=f"索引已过期 ({diff_desc})，建议重建。",
            snapshot_diff=differences
        )


def save_refs_snapshot(gimi_path: Path, snapshot: RefsSnapshot) -> None:
    """
    保存 refs 快照到文件

    Args:
        gimi_path: .gimi 目录路径
        snapshot: refs 快照对象
    """
    snapshot_path = get_refs_snapshot_path(gimi_path)
    snapshot.save(snapshot_path)


if __name__ == "__main__":
    import tempfile

    print("测试索引状态检查...")

    with tempfile.TemporaryDirectory() as tmpdir:
        gimi_path = Path(tmpdir) / ".gimi"
        gimi_path.mkdir(parents=True)

        # 创建子目录
        for subdir in ["index", "vectors", "cache", "logs"]:
            (gimi_path / subdir).mkdir(exist_ok=True)

        # 测试 1: 空索引目录（MISSING）
        print("\n测试 1: 空索引目录")
        # 创建空文件假装索引存在
        (gimi_path / "index" / "test.db").touch()

        health = check_index_health(gimi_path)
        print(f"  状态: {health.status.name}")
        print(f"  消息: {health.message}")

        # 测试 2: 无效的 refs 快照（CORRUPTED）
        print("\n测试 2: 无效的 refs 快照")
        # 创建一个空的 refs 快照文件
        empty_snapshot = RefsSnapshot(branches={}, tags={})
        save_refs_snapshot(gimi_path, empty_snapshot)

        # 现在应该能加载快照，但由于无法获取当前仓库 refs，结果取决于环境
        print("  已创建空 refs 快照")

        # 测试 3: 配置保存和加载
        print("\n测试 3: 配置保存和加载")
        config = GimiConfig()
        config.model.model = "gpt-4"
        config.retrieval.top_k = 25

        config_path = gimi_path / "config.json"
        config.save(config_path)
        print(f"  配置已保存到: {config_path}")

        loaded_config = GimiConfig.load(config_path)
        print(f"  加载的模型: {loaded_config.model.model}")
        print(f"  加载的 top_k: {loaded_config.retrieval.top_k}")

    print("\n所有测试完成!")
