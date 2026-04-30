"""Embedding model factory — centralises provider construction."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llama_index.core.embeddings import BaseEmbedding

from sage_mcp.settings import EmbeddingSettings


def make_embed_model(settings: EmbeddingSettings, api_key: str = "") -> BaseEmbedding:
    """Return the appropriate LlamaIndex embedding model for the configured provider."""
    if settings.provider == "openai":
        from llama_index.embeddings.openai import OpenAIEmbedding
        return OpenAIEmbedding(model=settings.model, api_key=api_key)

    if settings.provider == "ollama":
        from llama_index.embeddings.ollama import OllamaEmbedding
        kwargs: dict = {"model_name": settings.model}
        if settings.base_url:
            kwargs["base_url"] = settings.base_url
        return OllamaEmbedding(**kwargs)

    if settings.provider == "litellm":
        try:
            from llama_index.embeddings.litellm import LiteLLMEmbedding
        except ImportError as e:
            raise RuntimeError(
                "litellm provider requires 'llama-index-embeddings-litellm'. "
                "Install with: pip install 'sage-mcp[litellm]'"
            ) from e
        kwargs = {"model_name": settings.model}
        if settings.base_url:
            kwargs["api_base"] = settings.base_url
        if api_key:
            kwargs["api_key"] = api_key
        return LiteLLMEmbedding(**kwargs)

    raise ValueError(f"Unknown embedding provider: {settings.provider!r}")
