"""Tests for the CLI module."""

import pytest
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

from gimi.core.cli import create_parser, main, validate_environment


class TestCreateParser:
    """Tests for the argument parser."""

    def test_parser_requires_query(self):
        """Parser should require a query argument."""
        parser = create_parser()

        # Should raise error when query is missing
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parser_accepts_query(self):
        """Parser should accept a query."""
        parser = create_parser()
        args = parser.parse_args(['How do I implement X?'])

        assert args.query == 'How do I implement X?'

    def test_parser_accepts_file_option(self):
        """Parser should accept --file option."""
        parser = create_parser()
        args = parser.parse_args(['--file', 'src/main.py', 'How do I fix this?'])

        assert args.file_path == 'src/main.py'

    def test_parser_accepts_branch_option(self):
        """Parser should accept --branch option."""
        parser = create_parser()
        args = parser.parse_args(['--branch', 'develop', 'What changed?'])

        assert args.branch == 'develop'

    def test_parser_accepts_rebuild_flag(self):
        """Parser should accept --rebuild-index flag."""
        parser = create_parser()
        args = parser.parse_args(['--rebuild-index', 'Tell me about X'])

        assert args.rebuild_index is True

    def test_parser_accepts_top_k(self):
        """Parser should accept --top-k option."""
        parser = create_parser()
        args = parser.parse_args(['--top-k', '50', 'What should I do?'])

        assert args.top_k == 50

    def test_parser_accepts_verbose(self):
        """Parser should accept --verbose flag."""
        parser = create_parser()
        args = parser.parse_args(['--verbose', 'Explain this'])

        assert args.verbose is True


class TestValidateEnvironment:
    """Tests for environment validation."""

    @patch('gimi.core.cli.find_repo_root')
    def test_validate_environment_success(self, mock_find_root):
        """Should return repo root when in a git repo."""
        mock_find_root.return_value = '/path/to/repo'

        result = validate_environment()

        assert result == '/path/to/repo'

    @patch('gimi.core.cli.find_repo_root')
    @patch('gimi.core.cli.sys.exit')
    def test_validate_environment_failure(self, mock_exit, mock_find_root):
        """Should exit when not in a git repo."""
        mock_find_root.return_value = None
        mock_exit.side_effect = SystemExit(1)

        with pytest.raises(SystemExit):
            validate_environment()


class TestMain:
    """Tests for the main function."""

    @patch('gimi.core.cli.find_repo_root')
    def test_main_basic(self, mock_find_root):
        """Test basic main function execution."""
        # Setup
        mock_find_root.return_value = Path.cwd()

        # Run main with test arguments
        test_args = ['Test query']
        with patch.object(sys, 'argv', ['gimi'] + test_args):
            try:
                result = main()
                # We expect 0 (success) or 1 (error) but not an exception
                assert result in [0, 1]
            except SystemExit as e:
                # SystemExit with code 0 or 1 is acceptable
                assert e.code in [0, 1]

    @patch('gimi.core.cli.find_repo_root')
    @patch('gimi.core.cli.sys.exit')
    def test_main_not_git_repo(self, mock_exit, mock_find_root):
        """Test main when not in a git repository."""
        mock_find_root.return_value = None
        mock_exit.side_effect = SystemExit(1)

        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, 'argv', ['gimi', 'test query']):
                main()

        assert exc_info.value.code == 1
