"""
路径解析与.gimi目录管理
负责解析git仓库根目录和管理.gimi目录结构
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


class GimiPaths:
    """管理Gimi相关的所有路径"""

    GIMI_DIR_NAME = ".gimi"
    INDEX_DIR_NAME = "index"
    VECTORS_DIR_NAME = "vectors"
    CACHE_DIR_NAME = "cache"
    LOGS_DIR_NAME = "logs"
    CONFIG_FILE_NAME = "config.json"
    REFS_SNAPSHOT_FILE = "refs_snapshot.json"

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).absolute()
        self.gimi_dir = self.repo_root / self.GIMI_DIR_NAME

    @classmethod
    def from_current_directory(cls, cwd: Optional[Path] = None) -> "GimiPaths":
        """
        从当前目录解析git仓库根目录

        Args:
            cwd: 起始目录，默认为当前工作目录

        Returns:
            GimiPaths实例

        Raises:
            RuntimeError: 如果不在git仓库中
        """
        if cwd is None:
            cwd = Path.cwd()

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=True,
            )
            repo_root = Path(result.stdout.strip())
            return cls(repo_root)
        except subprocess.CalledProcessError:
            raise RuntimeError(
                "当前目录不是git仓库或其子目录。请在git仓库内执行gimi命令。"
            )
        except FileNotFoundError:
            raise RuntimeError("未找到git命令，请确保git已安装并加入PATH。")

    @property
    def index_dir(self) -> Path:
        return self.gimi_dir / self.INDEX_DIR_NAME

    @property
    def vectors_dir(self) -> Path:
        return self.gimi_dir / self.VECTORS_DIR_NAME

    @property
    def cache_dir(self) -> Path:
        return self.gimi_dir / self.CACHE_DIR_NAME

    @property
    def logs_dir(self) -> Path:
        return self.gimi_dir / self.LOGS_DIR_NAME

    @property
    def config_file(self) -> Path:
        return self.gimi_dir / self.CONFIG_FILE_NAME

    @property
    def refs_snapshot_file(self) -> Path:
        return self.gimi_dir / self.REFS_SNAPSHOT_FILE

    def ensure_directories(self) -> None:
        """确保所有必要的目录结构存在"""
        self.gimi_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def get_relative_path(self, path: Path) -> Path:
        """获取相对于仓库根目录的路径"""
        return Path(path).resolve().relative_to(self.repo_root)

    def get_absolute_path(self, relative_path: Path) -> Path:
        """从相对路径获取绝对路径"""
        return self.repo_root / relative_path
