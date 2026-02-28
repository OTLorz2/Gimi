"""Tests for the CLI module."""

import pytest
import sys
from unittest.mock import patch, MagicMock

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
    @patch('gimi.core.cli.get_gimi_dir')
    @patch('gimi.core.cli.ensure_gimi_structure')
    @patch('gimi.core.cli.load_config')
    @patch('gimi.core.cli.acquire_lock')
    @patch('gimi.core.cli.RequestLogger')
    @patch('gimi.core.cli.build_index_if_needed')
    @patch('gimi.core.cli.KeywordSearcher')
    @patch('gimi.core.cli.SemanticSearcher')
    @patch('gimi.core.cli.FusionRanker')
    @patch('gimi.core.cli.DiffFetcher')
    @patch('gimi.core.cli.PromptBuilder')
    @patch('gimi.core.cli.LLMClient')
    @patch('gimi.core.cli.OutputFormatter')
    @patch('gimi.core.cli.release_lock')
    def test_main_success_flow(self, mock_release_lock, mock_formatter, mock_llm,
                              mock_prompt, mock_diff, mock_fusion, mock_semantic,
                              mock_keyword, mock_build_index, mock_logger,
                              mock_acquire_lock, mock_config, mock_ensure,
                              mock_gimi_dir, mock_repo_root, capsys):
        """Test the main success flow."""
        # Setup mocks
        mock_repo_root.return_value = '/repo'
        mock_gimi_dir.return_value = '/repo/.gimi'
        mock_acquire_lock.return_value = True
        mock_config.return_value = MagicMock()
        mock_config.return_value.get.return_value = 25

        # Mock logger
        mock_logger_instance = MagicMock()
        mock_logger.return_value = mock_logger_instance
        mock_logger_instance.start_request.return_value = 'req-123'

        # Mock build_index
        mock_build_index.return_value = True

        # Mock keyword searcher
        mock_keyword_instance = MagicMock()
        mock_keyword.return_value = mock_keyword_instance
        mock_keyword_instance.search.return_value = [
            {'hash': 'abc123', 'message': 'Test commit'}
        ]

        # Mock semantic searcher
        mock_semantic_instance = MagicMock()
        mock_semantic.return_value = mock_semantic_instance
        mock_semantic_instance.is_available.return_value = False

        # Mock fusion ranker
        mock_fusion_instance = MagicMock()
        mock_fusion.return_value = mock_fusion_instance
        mock_fusion_instance.fuse.return_value = [
            {'hash': 'abc123', 'message': 'Test commit'}
        ]

        # Mock diff fetcher
        mock_diff_instance = MagicMock()
        mock_diff.return_value = mock_diff_instance
        mock_diff_instance.fetch.return_value = 'diff content'

        # Mock prompt builder
        mock_prompt_instance = MagicMock()
        mock_prompt.return_value = mock_prompt_instance
        mock_prompt_instance.build.return_value = 'prompt text'

        # Mock LLM client
        mock_llm_instance = MagicMock()
        mock_llm.return_value = mock_llm_instance
        mock_llm_instance.generate.return_value = {
            'text': 'Here is the suggestion',
            'duration': 1.5
        }

        # Mock output formatter
        mock_formatter_instance = MagicMock()
        mock_formatter.return_value = mock_formatter_instance
        mock_formatter_instance.format.return_value = 'Formatted output'

        # Run main with test arguments
        test_args = ['Test query']
        with patch.object(sys, 'argv', ['gimi'] + test_args):
            result = main()

        # Assertions
        assert result == 0
        mock_repo_root.assert_called_once()
        mock_acquire_lock.assert_called_once()
        mock_build_index.assert_called_once()
        mock_formatter_instance.format.assert_called_once()

        # Check output
        captured = capsys.readouterr()
        assert 'Formatted output' in captured.out

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


def cli_entry_point():
    """Entry point for the console script."""
    sys.exit(main())


if __name__ == '__main__':
    main()
