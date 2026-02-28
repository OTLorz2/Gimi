"""Tests for configuration management."""

import json
import tempfile
import unittest
from pathlib import Path

from gimi.core.config import (
    GimiConfig,
    RetrievalConfig,
    ContextConfig,
    LLMConfig,
    IndexConfig,
    load_config,
    save_config,
    init_config,
    get_config_path,
    ConfigError
)


class TestRetrievalConfig(unittest.TestCase):
    """Tests for RetrievalConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = RetrievalConfig()
        self.assertEqual(config.keyword_candidates, 100)
        self.assertEqual(config.top_k, 20)
        self.assertEqual(config.rerank_top_k, 10)
        self.assertFalse(config.enable_rerank)


class TestContextConfig(unittest.TestCase):
    """Tests for ContextConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ContextConfig()
        self.assertEqual(config.max_files_per_commit, 10)
        self.assertEqual(config.max_lines_per_file, 50)
        self.assertEqual(config.max_total_tokens, 4000)
        self.assertTrue(config.enable_cache)


class TestLLMConfig(unittest.TestCase):
    """Tests for LLMConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LLMConfig()
        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.model, "gpt-4o-mini")
        self.assertIsNone(config.api_key)
        self.assertEqual(config.max_tokens, 2000)
        self.assertEqual(config.temperature, 0.3)
        self.assertEqual(config.timeout, 60.0)


class TestIndexConfig(unittest.TestCase):
    """Tests for IndexConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = IndexConfig()
        self.assertIsNone(config.max_commits)
        self.assertIsNone(config.max_age_days)
        self.assertEqual(config.branches, ["main", "master"])
        self.assertFalse(config.include_all_branches)
        self.assertEqual(config.batch_size, 100)
        self.assertEqual(config.embedding_model, "sentence-transformers/all-MiniLM-L6-v2")
        self.assertEqual(config.embedding_dim, 384)


class TestGimiConfig(unittest.TestCase):
    """Tests for GimiConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = GimiConfig()
        self.assertIsInstance(config.retrieval, RetrievalConfig)
        self.assertIsInstance(config.context, ContextConfig)
        self.assertIsInstance(config.llm, LLMConfig)
        self.assertIsInstance(config.index, IndexConfig)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = GimiConfig()
        data = config.to_dict()
        self.assertIn("retrieval", data)
        self.assertIn("context", data)
        self.assertIn("llm", data)
        self.assertIn("index", data)

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "retrieval": {"top_k": 50},
            "llm": {"model": "gpt-4"}
        }
        config = GimiConfig.from_dict(data)
        self.assertEqual(config.retrieval.top_k, 50)
        self.assertEqual(config.llm.model, "gpt-4")


class TestConfigPersistence(unittest.TestCase):
    """Tests for config loading and saving."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.gimi_dir = Path(self.temp_dir) / ".gimi"
        self.gimi_dir.mkdir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        config = GimiConfig()
        config.llm.model = "gpt-4"
        config.retrieval.top_k = 50

        save_config(config, self.gimi_dir)

        loaded = load_config(self.gimi_dir)
        self.assertEqual(loaded.llm.model, "gpt-4")
        self.assertEqual(loaded.retrieval.top_k, 50)

    def test_get_config_path(self):
        """Test getting config file path."""
        path = get_config_path(self.gimi_dir)
        self.assertEqual(path, self.gimi_dir / "config.json")


if __name__ == "__main__":
    unittest.main()
