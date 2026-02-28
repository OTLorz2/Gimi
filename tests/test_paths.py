"""
测试路径解析模块
"""

import os
import tempfile
from pathlib import Path

import pytest

from gimi.utils.paths import GimiPaths


class TestGimiPaths:
    """测试GimiPaths类"""

    def test_init(self, tmp_path):
        """测试初始化"""
        repo_path = tmp_path / "test-repo"
        paths = GimiPaths(repo_path)
        assert paths.repo_root == repo_path.resolve()
        assert paths.gimi_dir == repo_path / ".gimi"

    def test_directories(self, tmp_path):
        """测试目录属性"""
        repo_path = tmp_path / "test-repo"
        paths = GimiPaths(repo_path)

        assert paths.index_dir == repo_path / ".gimi" / "index"
        assert paths.vectors_dir == repo_path / ".gimi" / "vectors"
        assert paths.cache_dir == repo_path / ".gimi" / "cache"
        assert paths.logs_dir == repo_path / ".gimi" / "logs"
        assert paths.config_file == repo_path / ".gimi" / "config.json"
        assert paths.refs_snapshot_file == repo_path / ".gimi" / "refs_snapshot.json"

    def test_ensure_directories(self, tmp_path):
        """测试创建目录"""
        repo_root = tmp_path / "test-repo"
        paths = GimiPaths(repo_root)

        # 确保目录存在
        paths.ensure_directories()

        # 验证目录已创建
        assert paths.gimi_dir.exists()
        assert paths.index_dir.exists()
        assert paths.vectors_dir.exists()
        assert paths.cache_dir.exists()
        assert paths.logs_dir.exists()


class TestGimiPathsFromCurrentDirectory:
    """测试从当前目录解析仓库"""

    def test_from_git_repo(self, tmp_path):
        """测试从git仓库解析"""
        # 创建临时git仓库
        repo_root = tmp_path / "test-repo"
        repo_root.mkdir()

        # 初始化git仓库
        import subprocess
        subprocess.run(
            ["git", "init"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )

        # 配置git用户
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )

        # 创建一个文件并提交
        test_file = repo_root / "test.txt"
        test_file.write_text("test content")
        subprocess.run(
            ["git", "add", "."],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=str(repo_root),
            check=True,
            capture_output=True,
        )

        # 测试从子目录解析
        subdir = repo_root / "subdir"
        subdir.mkdir()

        paths = GimiPaths.from_current_directory(subdir)

        assert paths.repo_root == repo_root.resolve()

    def test_not_git_repo(self, tmp_path):
        """测试非git目录报错"""
        import subprocess

        with pytest.raises(RuntimeError) as exc_info:
            GimiPaths.from_current_directory(tmp_path)

        assert "不是git仓库" in str(exc_info.value)
