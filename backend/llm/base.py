"""
LLM Provider Abstraction Layer
Defines the interface all providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class ProviderName(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    raw: dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMConfig:
    temperature: float = 0.2
    max_tokens: int = 2048
    top_p: float = 1.0
    stream: bool = False
    response_format: str | None = None  # "json" for structured output


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: ProviderName
    default_model: str

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """Send messages and return completion."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
        config: LLMConfig | None = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        ...

    async def health_check(self) -> bool:
        """Check if provider is available."""
        try:
            resp = await self.complete(
                [Message(role="user", content="ping")],
                config=LLMConfig(max_tokens=5),
            )
            return bool(resp.content)
        except Exception:
            return False
