import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from sage_mcp.searcher import search as do_search
from sage_mcp.settings import env, load_config
from sage_mcp.store import make_qdrant_client

mcp = FastMCP("sage-mcp")

_cfg = None
_client = None
_embed = None
_config_path: Path | None = None


def _init() -> None:
    global _cfg, _client, _embed
    if _cfg is not None:
        return

    from sage_mcp.settings import resolve_config_path
    config_path = _config_path or resolve_config_path()
    if not config_path.exists():
        raise RuntimeError(f"Config file not found: {config_path}")

    _cfg = load_config(config_path)
    _client = make_qdrant_client(_cfg.qdrant)

    if _cfg.embedding.provider == "openai" and not env.openai_api_key:
        msg = "OPENAI_API_KEY is not set. Add it to .env or set the environment variable."
        raise RuntimeError(msg)

    from sage_mcp.embeddings import make_embed_model
    _embed = make_embed_model(_cfg.embedding, env.openai_api_key)


@mcp.tool()
def search_kb(
    query: str,
    kb: str | None = None,
    top_k: int = 10,
    filter_type: str | None = None,
    filter_status: str | None = None,
    filter_kb_tags: str | None = None,
    filter_doc_tags: str | None = None,
) -> dict:
    """Search the knowledge base with hybrid semantic + keyword search.

    Args:
        query: Natural language search query.
        kb: Limit to a specific knowledge base name (e.g. 'homelab').
        top_k: Number of results to return (default 10).
        filter_type: Filter by frontmatter 'type' field (e.g. 'lxc', 'vm', 'idea').
        filter_status: Filter by frontmatter 'status' field (e.g. 'running', 'planned').
        filter_kb_tags: Comma-separated KB-level tags to filter by (OR logic). e.g. 'work,homelab'
        filter_doc_tags: Comma-separated document frontmatter tags to filter by (OR logic).
    """
    _init()

    metadata_filters = {}
    if filter_type:
        metadata_filters["type"] = filter_type
    if filter_status:
        metadata_filters["status"] = filter_status

    kb_tags = [t.strip() for t in filter_kb_tags.split(",")] if filter_kb_tags else None
    doc_tags = [t.strip() for t in filter_doc_tags.split(",")] if filter_doc_tags else None

    results, duplicates_removed = do_search(
        query,
        _client,
        _embed,
        _cfg.qdrant.collection,
        top_k=top_k,
        hybrid=_cfg.search.hybrid,
        kb_filter=kb,
        metadata_filters=metadata_filters or None,
        kb_tags=kb_tags,
        doc_tags=doc_tags,
    )

    return {
        "results": [
            {
                "score": r.score,
                "file_path": r.file_path,
                "kb": r.kb,
                "text": r.text,
                "metadata": r.metadata,
            }
            for r in results
        ],
        "duplicates_removed": duplicates_removed,
    }


@mcp.tool()
def list_knowledge_bases() -> list[dict]:
    """List all configured knowledge bases."""
    _init()
    return [
        {
            "name": kb.name,
            "path": str(kb.path),
            "description": kb.description,
            "extensions": kb.include_extensions,
        }
        for kb in _cfg.knowledge_bases
    ]


def main() -> None:
    global _config_path
    parser = argparse.ArgumentParser(description="sage-mcp server")
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to config.yaml (default: config.yaml in current working directory)",
    )
    args = parser.parse_args()
    if args.config is not None:
        _config_path = args.config
    mcp.run()


if __name__ == "__main__":
    main()
