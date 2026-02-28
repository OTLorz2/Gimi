"""Integration tests for Gimi."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestCLIIntegration(unittest.TestCase):
    """Integration tests for the CLI."""

    def setUp(self):
        """Create a temporary git repository."""
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

        # Configure git user
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )

        # Create initial commit
        test_file = self.repo_dir / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(
            ["git", "add", "."],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit with test file"],
            cwd=str(self.repo_dir),
            capture_output=True,
            check=True
        )

        # Add more commits for richer history
        for i in range(3):
            test_file.write_text(f"content version {i+2}")
            subprocess.run(
                ["git", "add", "."],
                cwd=str(self.repo_dir),
                capture_output=True,
                check=True
            )
            subprocess.run(
                ["git", "commit", "-m", f"Update test file - version {i+2}"],
                cwd=str(self.repo_dir),
                capture_output=True,
                check=True
            )

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        # Change back to original directory first
        os.chdir(self.repo_dir.parent.parent)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_help(self):
        """Test CLI help output."""
        import sys
        sys.path.insert(0, str(self.repo_dir.parent.parent))

        from gimi.core.cli import create_parser
        parser = create_parser()
        self.assertIsNotNone(parser)

    def test_repo_discovery(self):
        """Test repository discovery."""
        import sys
        sys.path.insert(0, str(self.repo_dir.parent.parent))

        from gimi.core.repo import find_repo_root, RepoError

        # Should find repo from within the repo
        found_root = find_repo_root(self.repo_dir)
        self.assertEqual(found_root.resolve(), self.repo_dir.resolve())

    def test_gimi_structure_creation(self):
        """Test .gimi directory structure creation."""
        import sys
        sys.path.insert(0, str(self.repo_dir.parent.parent))

        from gimi.core.repo import ensure_gimi_structure

        gimi_dir = ensure_gimi_structure(self.repo_dir)

        self.assertTrue(gimi_dir.exists())
        self.assertTrue((gimi_dir / "index").exists())
        self.assertTrue((gimi_dir / "vectors").exists())
        self.assertTrue((gimi_dir / "cache").exists())
        self.assertTrue((gimi_dir / "logs").exists())


if __name__ == "__main__":
    unittest.main()
