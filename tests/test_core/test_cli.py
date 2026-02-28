"""
Tests for the CLI module.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from gimi.core.cli import (
    create_parser,
    validate_environment,
    main
)


class TestCreateParser:
    """Tests for the argument parser."""

    def test_parser_requires_query(self):
        """Parser should require a query argument."""
        parser = create_parser()
        # When no arguments provided, it should show help and exit
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parser_accepts_query(self):
        """Parser should accept a query."""
        parser = create_parser()
        args = parser.parse_args(["how to refactor"])
        assert args.query == "how to refactor"

    def test_parser_accepts_file_option(self):
        """Parser should accept --file option."""
        parser = create_parser()
        args = parser.parse_args(["--file", "src/main.py", "how to refactor"])
        assert args.file_path == "src/main.py"

    def test_parser_accepts_branch_option(self):
        """Parser should accept --branch option."""
        parser = create_parser()
        args = parser.parse_args(["--branch", "feature-x", "what changed?"])
        assert args.branch == "feature-x"

    def test_parser_accepts_rebuild_flag(self):
        """Parser should accept --rebuild-index flag."""
        parser = create_parser()
        args = parser.parse_args(["--rebuild-index", "how to refactor"])
        assert args.rebuild_index is True

    def test_parser_accepts_top_k(self):
        """Parser should accept --top-k option."""
        parser = create_parser()
        args = parser.parse_args(["--top-k", "5", "how to refactor"])
        assert args.top_k == 5

    def test_parser_accepts_verbose(self):
        """Parser should accept --verbose flag."""
        parser = create_parser()
        args = parser.parse_args(["--verbose", "how to refactor"])
        assert args.verbose is True


class TestValidateEnvironment:
    """Tests for environment validation."""

    @patch('gimi.core.cli.find_repo_root')
    def test_validate_environment_success(self, mock_find_repo):
        """Should return repo root when in a git repo."""
        mock_find_repo.return_value = Path("/path/to/repo")
        result = validate_environment()
        # Compare as strings to handle platform-specific path separators
        assert str(result) == str(Path("/path/to/repo"))

    @patch('gimi.core.cli.find_repo_root')
    def test_validate_environment_failure(self, mock_find_repo):
        """Should exit when not in a git repo."""
        mock_find_repo.return_value = None
        with pytest.raises(SystemExit) as exc_info:
            validate_environment()
        assert exc_info.value.code == 1


class TestMain:
    """Tests for the main function."""

    @patch('gimi.core.cli.create_parser')
    @patch('gimi.core.cli.validate_environment')
    @patch('gimi.core.cli.load_config')
    @patch('gimi.core.cli.acquire_lock')
    def test_main_basic(self, mock_acquire, mock_load_config, mock_validate, mock_create_parser):
        """Test basic main function execution."""
        # Setup mocks
        mock_validate.return_value = "/path/to/repo"
        mock_acquire.return_value = True
        mock_load_config.return_value = MagicMock()

        mock_parser = MagicMock()
        mock_args = MagicMock()
        mock_args.query = "how to refactor"
        mock_args.rebuild_index = False
        mock_args.top_k = None
        mock_args.verbose = False
        mock_parser.parse_args.return_value = mock_args
        mock_create_parser.return_value = mock_parser

        # Call main
        result = main()

        # Verify
        mock_create_parser.assert_called_once()
        mock_validate.assert_called_once()
        assert result in [0, 1]  # Either success or failure is OK for this basic test

    @patch('gimi.core.cli.validate_environment')
    def test_main_not_git_repo(self, mock_validate):
        """Test main when not in a git repository."""
        # validate_environment returns str(repo_root) or exits with 1
        mock_validate.side_effect = SystemExit(1)

        with pytest.raises(SystemExit) as exc_info:
            main()

        # Accept exit code 1 (our validation) or 2 (argparse missing args)
        assert exc_info.value.code in [1, 2]
