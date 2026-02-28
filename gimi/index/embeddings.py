"""Embedding provider for generating commit embeddings."""

import os
from abc import ABC, abstractmethod
from typing import List, Optional


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimension of embeddings produced."""
        pass

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        pass

    def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        results = self.embed([text])
        return results[0] if results else []


class SentenceTransformerProvider(EmbeddingProvider):
    """Embedding provider using sentence-transformers."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize the provider.

        Args:
            model_name: Name of the sentence-transformers model
        """
        self.model_name = model_name
        self._model = None
        self._dimension = None

    def _load_model(self):
        """Lazy load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                # Get dimension from model config
                self._dimension = self._model.get_sentence_embedding_dimension()
            except ImportError:
                raise EmbeddingError(
                    "sentence-transformers is not installed. "
                    "Install it with: pip install sentence-transformers"
                )
            except Exception as e:
                raise EmbeddingError(f"Failed to load model {self.model_name}: {e}")

    @property
    def dimension(self) -> int:
        """Return the dimension of embeddings produced."""
        if self._dimension is None:
            self._load_model()
        return self._dimension or 384  # Default for all-MiniLM-L6-v2

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        if not texts:
            return []

        self._load_model()

        # Encode all texts
        try:
            embeddings = self._model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=False
            )
            # Convert to list of lists
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            raise EmbeddingError(f"Failed to generate embeddings: {e}")


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider using OpenAI API."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None
    ):
        """
        Initialize the provider.

        Args:
            model: Name of the OpenAI embedding model
            api_key: OpenAI API key (or use OPENAI_API_KEY env var)
            api_base: Custom API base URL (optional)
        """
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.api_base = api_base
        self._dimension = None

    @property
    def dimension(self) -> int:
        """Return the dimension of embeddings produced."""
        # Default dimensions for common models
        dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dimensions.get(self.model, 1536)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        if not texts:
            return []

        if not self.api_key:
            raise EmbeddingError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                "or pass api_key to the provider."
            )

        try:
            import openai
        except ImportError:
            raise EmbeddingError(
                "openai package is not installed. Install it with: pip install openai"
            )

        client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )

        try:
            # OpenAI has a limit of 2048 texts per request
            batch_size = 2048
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

            return all_embeddings
        except Exception as e:
            raise EmbeddingError(f"Failed to generate embeddings via OpenAI: {e}")


def get_embedding_provider(config) -> EmbeddingProvider:
    """
    Factory function to create an embedding provider based on config.

    Args:
        config: IndexConfig object

    Returns:
        EmbeddingProvider instance
    """
    from gimi.core.config import IndexConfig

    model = getattr(config, "embedding_model", "sentence-transformers/all-MiniLM-L6-v2")

    if model.startswith("sentence-transformers/"):
        return SentenceTransformerProvider(model_name=model)
    elif model in ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]:
        # OpenAI models
        from gimi.core.config import LLMConfig
        # Note: In real usage, we'd need to pass API key from LLM config
        return OpenAIEmbeddingProvider(model=model)
    else:
        # Default to sentence-transformers
        return SentenceTransformerProvider(model_name="sentence-transformers/all-MiniLM-L6-v2")
