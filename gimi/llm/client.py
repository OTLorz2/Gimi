"""LLM client implementations for Gimi."""

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any, Iterator, List


class LLMError(Exception):
    """Raised when LLM operations fail."""
    pass


@dataclass
class LLMResponse:
    """Response from LLM."""
    content: str
    model: str
    usage: Dict[str, int]
    latency_ms: float
    finish_reason: Optional[str] = None


@dataclass
class StreamingChunk:
    """A chunk of streaming response."""
    content: str
    is_finished: bool = False


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Get a completion from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific options

        Returns:
            LLMResponse with generated content
        """
        pass

    @abstractmethod
    def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[StreamingChunk]:
        """
        Stream completion from the LLM.

        Args:
            messages: List of message dicts
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific options

        Yields:
            StreamingChunk objects
        """
        pass


class OpenAIClient(LLMClient):
    """OpenAI API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        api_base: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize OpenAI client.

        Args:
            api_key: OpenAI API key (or use OPENAI_API_KEY env var)
            model: Model name
            api_base: Custom API base URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.api_base = api_base
        self.timeout = timeout

        if not self.api_key:
            raise LLMError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable.")

        try:
            import openai
            self._client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=self.timeout
            )
        except ImportError:
            raise LLMError("openai package not installed. Install with: pip install openai")

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Get completion from OpenAI."""
        start_time = time.time()

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )

            latency_ms = (time.time() - start_time) * 1000

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=self.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                },
                latency_ms=latency_ms,
                finish_reason=response.choices[0].finish_reason
            )
        except Exception as e:
            raise LLMError(f"OpenAI API error: {e}")

    def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[StreamingChunk]:
        """Stream completion from OpenAI."""
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield StreamingChunk(
                        content=chunk.choices[0].delta.content,
                        is_finished=False
                    )

            yield StreamingChunk(content="", is_finished=True)

        except Exception as e:
            raise LLMError(f"OpenAI streaming error: {e}")


class AnthropicClient(LLMClient):
    """Anthropic Claude API client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20240620",
        api_base: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize Anthropic client.

        Args:
            api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
            model: Model name
            api_base: Custom API base URL
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.api_base = api_base
        self.timeout = timeout

        if not self.api_key:
            raise LLMError("Anthropic API key not provided. Set ANTHROPIC_API_KEY environment variable.")

        try:
            import anthropic
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=self.timeout
            )
        except ImportError:
            raise LLMError("anthropic package not installed. Install with: pip install anthropic")

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Get completion from Anthropic."""
        start_time = time.time()

        # Convert messages to Anthropic format
        system_message = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        try:
            response = self._client.messages.create(
                model=self.model,
                messages=anthropic_messages,
                system=system_message,
                temperature=temperature,
                max_tokens=max_tokens or 2000,
                **kwargs
            )

            latency_ms = (time.time() - start_time) * 1000

            return LLMResponse(
                content=response.content[0].text if response.content else "",
                model=self.model,
                usage={
                    "input_tokens": response.usage.input_tokens if response.usage else 0,
                    "output_tokens": response.usage.output_tokens if response.usage else 0,
                    "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0
                },
                latency_ms=latency_ms,
                finish_reason=response.stop_reason
            )
        except Exception as e:
            raise LLMError(f"Anthropic API error: {e}")

    def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Iterator[StreamingChunk]:
        """Stream completion from Anthropic."""
        # Convert messages to Anthropic format
        system_message = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                anthropic_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        try:
            with self._client.messages.stream(
                model=self.model,
                messages=anthropic_messages,
                system=system_message,
                temperature=temperature,
                max_tokens=max_tokens or 2000,
                **kwargs
            ) as stream:
                for text in stream.text_stream:
                    yield StreamingChunk(content=text, is_finished=False)

            yield StreamingChunk(content="", is_finished=True)

        except Exception as e:
            raise LLMError(f"Anthropic streaming error: {e}")
