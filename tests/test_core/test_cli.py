"""
Tests for CLI entry and argument parsing (T3).
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from gimi.core.cli import (
    cli,
    parse_args,
    validate_args,
    CLIError
)


class TestParseArgs:
    """Tests for argument parsing."""

    def test_parse_ask_command(self):
        """Test parsing the ask command."""
        with patch('sys.argv', ['gimi', 'ask', 'How do I refactor this?']):
            args = parse_args()
            assert args.command == 'ask'
            assert args.query == 'How do I refactor this?'

    def test_parse_ask_with_file(self):
        """Test parsing ask command with --file option."""
        with patch('sys.argv', ['gimi', 'ask', '--file', 'src/main.py', 'How does this work?']):
            args = parse_args()
            assert args.file == 'src/main.py'

    def test_parse_ask_with_branch(self):
        """Test parsing ask command with --branch option."""
        with patch('sys.argv', ['gimi', 'ask', '--branch', 'feature-x', 'What changed?']):
            args = parse_args()
            assert args.branch == 'feature-x'

    def test_parse_index_command(self):
        """Test parsing the index command."""
        with patch('sys.argv', ['gimi', 'index']):
            args = parse_args()
            assert args.command == 'index'

    def test_parse_index_with_force(self):
        """Test parsing index command with --force option."""
        with patch('sys.argv', ['gimi', 'index', '--force']):
            args = parse_args()
            assert args.force is True

    def test_parse_config_command(self):
        """Test parsing the config command."""
        with patch('sys.argv', ['gimi', 'config']):
            args = parse_args()
            assert args.command == 'config'

    def test_parse_config_with_set(self):
        """Test parsing config command with --set option."""
        with patch('sys.argv', ['gimi', 'config', '--set', 'llm.model=claude-3']):
            args = parse_args()
            assert args.set == 'llm.model=claude-3'

    def test_parse_no_command_shows_help(self):
        """Test that running with no command shows help."""
        with patch('sys.argv', ['gimi']):
            with pytest.raises(SystemExit) as exc_info:
                parse_args()
            assert exc_info.value.code == 0


class TestValidateArgs:
    """Tests for argument validation."""

    def test_validate_ask_with_query(self):
        """Test validating ask command with query."""
        args = MagicMock()
        args.command = 'ask'
        args.query = 'How do I do this?'

        # Should not raise
        validate_args(args)

    def test_validate_ask_without_query(self):
        """Test validating ask command without query."""
        args = MagicMock()
        args.command = 'ask'
        args.query = None

        with pytest.raises(CLIError) as exc_info:
            validate_args(args)
        assert "query is required" in str(exc_info.value)

    def test_validate_index_command(self):
        """Test validating index command."""
        args = MagicMock()
        args.command = 'index'

        # Should not raise
        validate_args(args)

    def test_validate_config_command(self):
        """Test validating config command."""
        args = MagicMock()
        args.command = 'config'

        # Should not raise
        validate_args(args)


class TestCLI:
    """Tests for the main CLI entry point."""

    @patch('gimi.core.cli.parse_args')
    @patch('gimi.core.cli.validate_args')
    @patch('gimi.core.cli.handle_ask_command')
    def test_cli_ask_command(self, mock_handle, mock_validate, mock_parse):
        """Test CLI with ask command."""
        args = MagicMock()
        args.command = 'ask'
        mock_parse.return_value = args

        cli()

        mock_parse.assert_called_once()
        mock_validate.assert_called_once_with(args)
        mock_handle.assert_called_once_with(args)

    @patch('gimi.core.cli.parse_args')
    @patch('gimi.core.cli.validate_args')
    @patch('gimi.core.cli.handle_index_command')
    def test_cli_index_command(self, mock_handle, mock_validate, mock_parse):
        """Test CLI with index command."""
        args = MagicMock()
        args.command = 'index'
        mock_parse.return_value = args

        cli()

        mock_handle.assert_called_once_with(args)

    @patch('gimi.core.cli.parse_args')
    @patch('gimi.core.cli.validate_args')
    @patch('gimi.core.cli.handle_config_command')
    def test_cli_config_command(self, mock_handle, mock_validate, mock_parse):
        """Test CLI with config command."""
        args = MagicMock()
        args.command = 'config'
        mock_parse.return_value = args

        cli()

        mock_handle.assert_called_once_with(args)

    @patch('gimi.core.cli.parse_args')
    @patch('gimi.core.cli.validate_args')
    def test_cli_validation_error(self, mock_validate, mock_parse):
        """Test CLI handling of validation errors."""
        args = MagicMock()
        mock_parse.return_value = args
        mock_validate.side_effect = CLIError("Invalid arguments")

        with pytest.raises(SystemExit) as exc_info:
            cli()
        assert exc_info.value.code == 1

    @patch('gimi.core.cli.parse_args')
    @patch('gimi.core.cli.validate_args')
    @patch('gimi.core.cli.handle_ask_command')
    def test_cli_unexpected_error(self, mock_handle, mock_validate, mock_parse):
        """Test CLI handling of unexpected errors."""
        args = MagicMock()
        args.command = 'ask'
        mock_parse.return_value = args
        mock_handle.side_effect = Exception("Unexpected error")

        with pytest.raises(SystemExit) as exc_info:
            cli()
        assert exc_info.value.code == 2
