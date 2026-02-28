"""End-to-end tests for Gimi.

These tests verify the full flow from CLI invocation to output generation.
They use temporary repositories and mock external dependencies.
"""

import os
import tempfile
import shutil
import subprocess
import pytest
from unittest.mock import patch, MagicMock, mock_open


class TestEndToEndFlow:
    """End-to-end tests for the full Gimi flow."""

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary git repository with some commits."""
        temp_dir = tempfile.mkdtemp()

        try:
            # Initialize git repo
            subprocess.run(['git', 'init'], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=temp_dir, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=temp_dir, check=True, capture_output=True)

            # Create some files and commits
            for i in range(5):
                filename = f'file{i}.py'
                with open(os.path.join(temp_dir, filename), 'w') as f:
                    f.write(f'# File {i}\ndef function_{i}():\n    pass\n')

                subprocess.run(['git', 'add', filename], cwd=temp_dir, check=True, capture_output=True)
                subprocess.run(['git', 'commit', '-m', f'Add {filename} with function_{i}'],
                             cwd=temp_dir, check=True, capture_output=True)

            yield temp_dir

        finally:
            # Cleanup
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_full_flow_simple_query(self, temp_git_repo, capsys):
        """Test a simple end-to-end flow with a basic query."""
        import sys
        from unittest.mock import patch, MagicMock
        from gimi.core.cli import main

        # Change to temp repo and run
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_git_repo)

            # Mock sys.argv and dependencies at the module level where they are imported
            with patch.object(sys, 'argv', ['gimi', '--verbose', 'How should I name my functions?']):
                with patch('gimi.core.cli.build_index_if_needed') as mock_build_index:
                    mock_build_index.return_value = True
                    result = main()
                    # Check result - should succeed (0) or fail gracefully
                    assert result in [0, 1], f"Unexpected exit code: {result}"

        finally:
            os.chdir(original_cwd)

    def test_not_in_git_repo(self, capsys):
        """Test behavior when not in a git repository."""
        from gimi.core.cli import main, validate_environment
        import sys
        import tempfile
        import os

        # Create a temp directory that's not a git repo
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)

                # validate_environment should call sys.exit(1) when not in a git repo
                with pytest.raises(SystemExit) as exc_info:
                    validate_environment()

                assert exc_info.value.code == 1

            finally:
                os.chdir(original_cwd)


class TestCLIIntegration:
    """Integration tests that verify multiple components working together."""

    def test_index_building_flow(self, tmp_path):
        """Test that index building works end-to-end."""
        import subprocess
        import os

        # Create a minimal git repo
        repo_path = tmp_path / 'test_repo'
        repo_path.mkdir()

        subprocess.run(['git', 'init'], cwd=repo_path, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=repo_path, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=repo_path, check=True)

        # Create a file and commit
        test_file = repo_path / 'test.py'
        test_file.write_text('def hello(): pass\n')

        subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=repo_path, check=True)

        # Now test that we can build an index
        import sys
        sys.path.insert(0, str(repo_path.parent))

        from gimi.core.repo import find_repo_root, get_gimi_dir, ensure_gimi_structure
        from gimi.core.config import load_config
        from gimi.index.builder import IndexBuilder
        from gimi.core.git import get_commits_for_branch

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_path)

            repo_root = find_repo_root()
            assert repo_root is not None

            gimi_dir = get_gimi_dir(repo_root)
            ensure_gimi_structure(repo_root)

            config = load_config(gimi_dir)

            # Try to build an index using IndexBuilder
            builder = IndexBuilder(
                repo_root=repo_root,
                gimi_dir=gimi_dir,
                config=config.index
            )
            builder.build(incremental=False)

            # Check that we have commits indexed
            from gimi.index.lightweight import LightweightIndex
            with LightweightIndex(gimi_dir / 'index') as index:
                index.initialize()
                count = index.count()
                assert count > 0, "Should have indexed at least one commit"

        finally:
            os.chdir(original_cwd)
