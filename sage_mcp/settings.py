import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KnowledgeBase(BaseModel):
    name: str = Field(description="Unique identifier for this knowledge base")
    path: Path = Field(description="Absolute or ~ path to the KB root directory")
    description: str = Field(default="", description="Human-readable description")
    tags: list[str] = Field(default=[], description="Tags for filtering (e.g. [work, homelab])")
    include_extensions: list[str] = Field(
        default=[".md"], description="File extensions to index (e.g. [.md, .py, .txt])")
    exclude_patterns: list[str] = Field(
        default=[], description="Glob patterns to exclude (e.g. ['*.min.js', '**/generated/*'])")


class EmbeddingSettings(BaseModel):
    provider: Literal["openai", "ollama", "litellm"] = Field(
        default="openai", description="Embedding provider: openai, ollama, or litellm")
    model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model name (provider-specific)")
    base_url: str | None = Field(
        default=None, description="Override base URL (e.g. for Ollama: http://localhost:11434)")


class QdrantSettings(BaseModel):
    mode: Literal["local", "server"] = Field(
        default="local", description="local = embedded file store; server = remote Qdrant")
    path: Path | None = Field(
        default=None, description="Path for local Qdrant storage (default: XDG data dir)")
    collection: str = Field(default="kb", description="Qdrant collection name")
    host: str = Field(default="localhost", description="Qdrant server host (server mode only)")
    port: int = Field(default=6333, description="Qdrant server port (server mode only)")


class SearchSettings(BaseModel):
    top_k: int = Field(default=10, description="Default number of search results")
    hybrid: bool = Field(
        default=True, description="Use hybrid search (dense + BM25). Set false for dense-only.")


class Config(BaseModel):
    knowledge_bases: list[KnowledgeBase] = Field(
        description="List of knowledge bases to index and search")
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    openai_api_key: str = ""


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())
    return Config.model_validate(raw)


env = Env()


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _xdg_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def resolve_config_path() -> Path:
    """Return config path: CWD/config.yaml if it exists, else XDG default."""
    cwd_cfg = Path.cwd() / "config.yaml"
    if cwd_cfg.exists():
        return cwd_cfg
    return _xdg_config_home() / "sage-mcp" / "config.yaml"


def resolve_cache_dir() -> Path:
    """Return pipeline_cache directory: XDG cache home."""
    return _xdg_cache_home() / "sage-mcp" / "pipeline_cache"


def resolve_data_dir() -> Path:
    """Return Qdrant storage directory: XDG data home."""
    return _xdg_data_home() / "sage-mcp" / "qdrant"
