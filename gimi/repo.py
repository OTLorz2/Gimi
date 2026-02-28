"""
T1: 仓库解析与 .gimi 目录创建

功能：
- 用 `git rev-parse --show-toplevel` 解析 repo root
- 若失败则报错退出
- 创建/确认 `.gimi` 及子目录（index、vectors、cache、logs）
"""

import os
import subprocess
from pathlib import Path
from typing import Tuple, Optional


class RepoResolver:
    """解析 git 仓库根目录，管理 .gimi 目录结构"""

    GIMI_DIR = ".gimi"
    INDEX_DIR = "index"
    VECTORS_DIR = "vectors"
    CACHE_DIR = "cache"
    LOGS_DIR = "logs"

    def __init__(self, cwd: Optional[Path] = None):
        self.cwd = cwd or Path.cwd()
        self.repo_root: Optional[Path] = None
        self.gimi_path: Optional[Path] = None

    def resolve_repo_root(self) -> Path:
        """
        使用 git rev-parse --show-toplevel 解析仓库根目录

        Returns:
            Path: 仓库根目录的绝对路径

        Raises:
            RuntimeError: 如果当前目录不在 git 仓库中
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=self.cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            repo_root = Path(result.stdout.strip()).resolve()
            self.repo_root = repo_root
            return repo_root
        except subprocess.CalledProcessError:
            raise RuntimeError(
                f"当前目录 '{self.cwd}' 不在 git 仓库中。\n"
                "请在 git 仓库内执行此命令。"
            )

    def ensure_gimi_structure(self) -> Path:
        """
        确保 .gimi 目录及其子目录存在

        Returns:
            Path: .gimi 目录的绝对路径
        """
        if self.repo_root is None:
            self.resolve_repo_root()

        self.gimi_path = self.repo_root / self.GIMI_DIR

        # 创建子目录
        subdirs = [
            self.INDEX_DIR,
            self.VECTORS_DIR,
            self.CACHE_DIR,
            self.LOGS_DIR,
        ]

        for subdir in subdirs:
            (self.gimi_path / subdir).mkdir(parents=True, exist_ok=True)

        return self.gimi_path

    def get_paths(self) -> dict:
        """
        获取所有相关路径

        Returns:
            dict: 包含 repo_root, gimi_path, 以及各子目录路径
        """
        if self.repo_root is None:
            self.resolve_repo_root()

        if self.gimi_path is None:
            self.ensure_gimi_structure()

        return {
            "repo_root": self.repo_root,
            "gimi_path": self.gimi_path,
            "index_dir": self.gimi_path / self.INDEX_DIR,
            "vectors_dir": self.gimi_path / self.VECTORS_DIR,
            "cache_dir": self.gimi_path / self.CACHE_DIR,
            "logs_dir": self.gimi_path / self.LOGS_DIR,
        }


def initialize_repo(cwd: Optional[Path] = None) -> Tuple[Path, Path]:
    """
    初始化仓库环境：解析 repo root 并创建 .gimi 结构

    Args:
        cwd: 当前工作目录，默认为 Path.cwd()

    Returns:
        Tuple[Path, Path]: (repo_root, gimi_path)
    """
    resolver = RepoResolver(cwd)
    repo_root = resolver.resolve_repo_root()
    gimi_path = resolver.ensure_gimi_structure()
    return repo_root, gimi_path


if __name__ == "__main__":
    # 简单测试
    try:
        repo_root, gimi_path = initialize_repo()
        print(f"仓库根目录: {repo_root}")
        print(f".gimi 目录: {gimi_path}")

        resolver = RepoResolver()
        paths = resolver.get_paths()
        for name, path in paths.items():
            print(f"  {name}: {path}")
    except RuntimeError as e:
        print(f"错误: {e}")
        exit(1)
