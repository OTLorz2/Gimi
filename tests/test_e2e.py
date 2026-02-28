"""End-to-end tests for Gimi.

These tests verify the full flow from CLI invocation to output generation.
They use temporary repositories and mock external dependencies.
"""

import os
import tempfile
import shutil
import subprocess
import pytest
from unittest.mock import patch, MagicMock


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

    @patch('gimi.core.cli.LLMClient')
    @patch('gimi.core.cli.SemanticSearcher')
    @patch('gimi.core.cli.VectorIndex')
    def test_full_flow_simple_query(self, mock_vector_index, mock_semantic_searcher, mock_llm_client,
                                     temp_git_repo, capsys):
        """Test a simple end-to-end flow with a basic query."""
        from gimi.core.cli import main

        # Setup mocks
        mock_llm_instance = MagicMock()
        mock_llm_client.return_value = mock_llm_instance
        mock_llm_instance.generate.return_value = {
            'text': 'Based on the commit history, you should implement functions with clear naming like "function_0", "function_1", etc.',
            'duration': 0.5
        }

        mock_semantic_instance = MagicMock()
        mock_semantic_searcher.return_value = mock_semantic_instance
        mock_semantic_instance.is_available.return_value = False

        # Change to temp repo and run
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_git_repo)

            # Mock sys.argv
            import sys
            with patch.object(sys, 'argv', ['gimi', '--verbose', 'How should I name my functions?']):
                result = main()

            # Check result
            assert result == 0, f"Expected exit code 0, got {result}"

            # Check output
            captured = capsys.readouterr()
            assert 'Based on the commit history' in captured.out or 'Building' in captured.out or 'Indexing' in captured.out

        finally:
            os.chdir(original_cwd)

    def test_not_in_git_repo(self, capsys):
        """Test behavior when not in a git repository."""
        from gimi.core.cli import main
        import sys
        import tempfile
        import os

        # Create a temp directory that's not a git repo
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)

                with patch.object(sys, 'argv', ['gimi', 'test query']):
                    result = main()

                assert result == 1

                captured = capsys.readouterr()
                assert 'Not a git repository' in captured.err or 'Error' in captured.err

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
        from gimi.index.writer import IndexWriter
        from gimi.index.git import traverse_commits

        original_cwd = os.getcwd()
        try:
            os.chdir(repo_path)

            repo_root = find_repo_root()
            assert repo_root is not None

            gimi_dir = get_gimi_dir(repo_root)
            ensure_gimi_structure(repo_root)

            config = load_config(gimi_dir)

            # Try to build an index
            index_dir = str(repo_path / '.gimi' / 'index')
            writer = IndexWriter(index_dir)

            count = 0
            for commit_data in traverse_commits(str(repo_root), 'HEAD', limit=10):
                writer.write_commit(commit_data)
                count += 1

            writer.close()

            assert count > 0, "Should have indexed at least one commit"

        finally:
            os.chdir(original_cwd)
