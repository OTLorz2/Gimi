"""Tests for repository discovery."""

import os
import tempfile
import subprocess
from pathlib import Path
import unittest

from gimi.core.repo import (
    find_repo_root,
    ensure_gimi_structure,
    get_gimi_dir,
    RepoError
)


class TestFindRepoRoot(unittest.TestCase):
    """Tests for find_repo_root function."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = Path(self.temp_dir) / "test_repo"
        self.repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_root_in_repo_root(self):
        """Test finding root from repo root."""
        root = find_repo_root(self.repo_dir)
        self.assertEqual(root.resolve(), self.repo_dir.resolve())

    def test_find_root_in_subdir(self):
        """Test finding root from subdirectory."""
        subdir = self.repo_dir / "src" / "components"
        subdir.mkdir(parents=True)

        root = find_repo_root(subdir)
        self.assertEqual(root.resolve(), self.repo_dir.resolve())

    def test_find_root_not_in_repo(self):
        """Test error when not in a git repo."""
        non_repo = tempfile.mkdtemp()

        try:
            with self.assertRaises(RepoError) as ctx:
                find_repo_root(Path(non_repo))
            self.assertIn("Not a git repository", str(ctx.exception))
        finally:
            import shutil
            shutil.rmtree(non_repo, ignore_errors=True)


class TestGimiDirectory(unittest.TestCase):
    """Tests for .gimi directory management."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.repo_dir = Path(self.temp_dir) / "test_repo"
        self.repo_dir.mkdir()

        subprocess.run(
            ["git", "init"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_gimi_dir(self):
        """Test getting .gimi directory path."""
        gimi_dir = get_gimi_dir(self.repo_dir)
        self.assertEqual(gimi_dir, self.repo_dir / ".gimi")

    def test_ensure_gimi_structure(self):
        """Test creating .gimi structure."""
        gimi_dir = ensure_gimi_structure(self.repo_dir)

        self.assertTrue(gimi_dir.exists())
        self.assertTrue((gimi_dir / "index").exists())
        self.assertTrue((gimi_dir / "vectors").exists())
        self.assertTrue((gimi_dir / "cache").exists())
        self.assertTrue((gimi_dir / "logs").exists())


if __name__ == "__main__":
    unittest.main()
