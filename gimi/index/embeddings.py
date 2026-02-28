"""Embedding providers for vector indexing.

This module provides different embedding providers for generating
vector representations of text. It includes:
- MockEmbeddingProvider: For testing without real embeddings
- LocalEmbeddingProvider: Using sentence-transformers models
- APIEmbeddingProvider: Using external API services
"""

import os
import json
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import numpy as np


class EmbeddingError(Exception):
    """Raised when embedding operations fail."""
    pass


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    def __init__(self, dimension: int = 384, cache_dir: Optional[Path] = None):
        """Initialize the embedding provider.

        Args:
            dimension: Embedding dimension
            cache_dir: Directory for caching embeddings
        """
        self.dimension = dimension
        self.cache_dir = cache_dir
        if cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for texts.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embeddings with shape (len(texts), dimension)
        """
        pass

    def embed_single(self, text: str) -> np.ndarray:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector with shape (dimension,)
        """
        embeddings = self.embed([text])
        return embeddings[0]

    def _get_cache_path(self, text: str) -> Optional[Path]:
        """Get cache file path for a text.

        Args:
            text: Text to get cache path for

        Returns:
            Cache file path or None if no cache_dir
        """
        if not self.cache_dir:
            return None

        # Use hash of text as filename
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        return self.cache_dir / f"{text_hash}.json"

    def _load_cached(self, text: str) -> Optional[np.ndarray]:
        """Load cached embedding for text.

        Args:
            text: Text to load cache for

        Returns:
            Cached embedding or None
        """
        cache_path = self._get_cache_path(text)
        if not cache_path or not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            return np.array(data['embedding'], dtype=np.float32)
        except (json.JSONDecodeError, KeyError, ValueError):
            # Invalid cache, remove it
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None

    def _save_cached(self, text: str, embedding: np.ndarray) -> None:
        """Save embedding to cache.

        Args:
            text: Text to cache embedding for
            embedding: Embedding vector
        """
        cache_path = self._get_cache_path(text)
        if not cache_path:
            return

        try:
            data = {
                'text_hash': hashlib.sha256(text.encode()).hexdigest()[:16],
                'embedding': embedding.tolist(),
                'dimension': len(embedding)
            }
            with open(cache_path, 'w') as f:
                json.dump(data, f)
        except (OSError, TypeError):
            pass


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider for testing.

    Generates deterministic pseudo-random embeddings based on text hash.
    """

    def __init__(self, dimension: int = 384, cache_dir: Optional[Path] = None, seed: int = 42):
        """Initialize mock provider.

        Args:
            dimension: Embedding dimension
            cache_dir: Cache directory (unused for mock)
            seed: Random seed for deterministic embeddings
        """
        super().__init__(dimension=dimension, cache_dir=None)  # No caching for mock
        self.seed = seed

    def embed(self, texts: List[str]) -> np.ndarray:
        """Generate deterministic mock embeddings.

        Args:
            texts: List of texts to embed

        Returns:
            Array of deterministic embeddings
        """
        embeddings = []
        for text in texts:
            # Use hash of text to seed the random generator
            text_hash = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
            np.random.seed((self.seed + text_hash) % (2**32))

            # Generate normalized random vector
            vec = np.random.randn(self.dimension).astype(np.float32)
            vec = vec / np.linalg.norm(vec)
            embeddings.append(vec)

        return np.array(embeddings)


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local embedding provider using sentence-transformers.

    This provider loads a local model and generates embeddings on-device.
    It's suitable for offline use and doesn't require API calls.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_dir: Optional[Path] = None,
        device: Optional[str] = None,
        batch_size: int = 32
    ):
        """Initialize local embedding provider.

        Args:
            model_name: Name of the sentence-transformers model
            cache_dir: Directory for caching embeddings
            device: Device to use ('cpu', 'cuda', etc.)
            batch_size: Batch size for embedding generation
        """
        self.model_name = model_name
        self.device = device or 'cpu'
        self.batch_size = batch_size
        self._model = None

        # Determine dimension based on model
        dimensions = {
            'all-MiniLM-L6-v2': 384,
            'all-MiniLM-L12-v2': 384,
            'all-mpnet-base-v2': 768,
            'paraphrase-MiniLM-L6-v2': 384,
            'paraphrase-MiniLM-L3-v2': 384,
        }
        dimension = dimensions.get(model_name, 384)

        super().__init__(dimension=dimension, cache_dir=cache_dir)

    def _load_model(self):
        """Lazy load the sentence-transformers model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
        except ImportError:
            raise EmbeddingError(
                f"sentence-transformers is required for LocalEmbeddingProvider. "
                f"Install with: pip install sentence-transformers"
            )
        except Exception as e:
            raise EmbeddingError(f"Failed to load model {self.model_name}: {e}")

    def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using the local model.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embeddings
        """
        if not texts:
            return np.array([])

        # Check cache first
        cached_embeddings = []
        texts_to_embed = []
        indices = []

        for i, text in enumerate(texts):
            cached = self._load_cached(text)
            if cached is not None:
                cached_embeddings.append((i, cached))
            else:
                texts_to_embed.append(text)
                indices.append(i)

        # Generate embeddings for non-cached texts
        if texts_to_embed:
            self._load_model()

            try:
                embeddings = self._model.encode(
                    texts_to_embed,
                    batch_size=self.batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True
                )
            except Exception as e:
                raise EmbeddingError(f"Failed to generate embeddings: {e}")

            # Cache the new embeddings
            for idx, text, emb in zip(indices, texts_to_embed, embeddings):
                self._save_cached(text, emb)
                cached_embeddings.append((idx, emb))

        # Reconstruct in original order
        cached_embeddings.sort(key=lambda x: x[0])
        result = np.array([emb for _, emb in cached_embeddings])

        return result


class APIEmbeddingProvider(EmbeddingProvider):
    """API-based embedding provider.

    Uses external APIs like OpenAI, Cohere, or other embedding services.
    """

    def __init__(
        self,
        api_key: str,
        api_base: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        cache_dir: Optional[Path] = None,
        batch_size: int = 100,
        provider: str = "openai"
    ):
        """Initialize API embedding provider.

        Args:
            api_key: API key for the service
            api_base: Base URL for the API
            model: Model name to use
            dimension: Embedding dimension
            cache_dir: Directory for caching embeddings
            batch_size: Batch size for API calls
            provider: Provider name ('openai', 'cohere', etc.)
        """
        super().__init__(dimension=dimension, cache_dir=cache_dir)

        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.batch_size = batch_size
        self.provider = provider

    def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings via API.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embeddings
        """
        if not texts:
            return np.array([])

        # Check cache first
        cached_embeddings = []
        texts_to_embed = []
        indices = []

        for i, text in enumerate(texts):
            cached = self._load_cached(text)
            if cached is not None:
                cached_embeddings.append((i, cached))
            else:
                texts_to_embed.append(text)
                indices.append(i)

        # Call API for non-cached texts
        if texts_to_embed:
            try:
                embeddings = self._call_api(texts_to_embed)
            except Exception as e:
                raise EmbeddingError(f"API call failed: {e}")

            # Cache the new embeddings
            for idx, text, emb in zip(indices, texts_to_embed, embeddings):
                self._save_cached(text, emb)
                cached_embeddings.append((idx, emb))

        # Reconstruct in original order
        cached_embeddings.sort(key=lambda x: x[0])
        result = np.array([emb for _, emb in cached_embeddings])

        return result

    def _call_api(self, texts: List[str]) -> np.ndarray:
        """Make API call to get embeddings.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embeddings
        """
        if self.provider == "openai":
            return self._call_openai(texts)
        else:
            raise EmbeddingError(f"Unsupported provider: {self.provider}")

    def _call_openai(self, texts: List[str]) -> np.ndarray:
        """Call OpenAI API for embeddings.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embeddings
        """
        import requests

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        embeddings = []

        # Process in batches
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]

            data = {
                "input": batch,
                "model": self.model
            }

            response = requests.post(
                f"{self.api_base}/embeddings",
                headers=headers,
                json=data,
                timeout=60
            )

            if response.status_code != 200:
                raise EmbeddingError(
                    f"OpenAI API error: {response.status_code} - {response.text}"
                )

            result = response.json()
            batch_embeddings = [item["embedding"] for item in result["data"]]
            embeddings.extend(batch_embeddings)

        return np.array(embeddings, dtype=np.float32)


def get_embedding_provider(config) -> EmbeddingProvider:
    """Get embedding provider based on configuration.

    Args:
        config: Index configuration object

    Returns:
        EmbeddingProvider instance
    """
    provider_type = getattr(config, 'embedding_provider', 'mock')
    dimension = getattr(config, 'embedding_dimension', 384)
    cache_dir = getattr(config, 'embedding_cache_dir', None)

    if provider_type == 'local':
        model_name = getattr(config, 'embedding_model', 'all-MiniLM-L6-v2')
        return LocalEmbeddingProvider(
            model_name=model_name,
            dimension=dimension,
            cache_dir=Path(cache_dir) if cache_dir else None
        )
    elif provider_type == 'openai':
        api_key = getattr(config, 'embedding_api_key', os.environ.get('OPENAI_API_KEY', ''))
        api_base = getattr(config, 'embedding_api_base', 'https://api.openai.com/v1')
        model = getattr(config, 'embedding_model', 'text-embedding-3-small')
        return APIEmbeddingProvider(
            api_key=api_key,
            api_base=api_base,
            model=model,
            dimension=dimension,
            cache_dir=Path(cache_dir) if cache_dir else None,
            provider='openai'
        )
    else:
        # Default to mock provider for testing
        return MockEmbeddingProvider(dimension=dimension)
