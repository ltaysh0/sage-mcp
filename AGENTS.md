# AGENTS.md

**Generated:** 2026-04-28
**Commit:** 551713a (+ unstaged)
**Branch:** main

## Overview

Standalone hybrid semantic search (dense vector + BM25) over local knowledge bases and codebases. Stack: LlamaIndex · Qdrant embedded · OpenAI/Ollama/LiteLLM embeddings · FastMCP. Exposes a CLI (`sage-mcp`) and an MCP server (`sage-mcp-mcp`) for AI agents.

## Structure

```
sage-mcp/
├── sage_mcp/          # Package — all runtime logic
│   ├── settings.py     # Pydantic config models; module-level `env` singleton; XDG path helpers
│   ├── embeddings.py   # Embedding model factory: make_embed_model() — openai/ollama/litellm
│   ├── parsing.py      # load_document(), parse_nodes(), wikilink/frontmatter handling
│   ├── store.py        # Qdrant client factory (local path or server)
│   ├── indexer.py      # Ingestion pipeline; hash cache v1/v2; parallel dir walk + embed
│   ├── searcher.py     # Hybrid retrieval; dedup; kb_tags/doc_tags filtering
│   ├── graph.py        # File-level semantic similarity graph builder; JSON/GraphML/DOT export
│   ├── cli/            # Typer CLI package (split by command)
│   │   ├── __init__.py      # Imports all submodules; re-exports app, config_app, console
│   │   ├── _common.py       # Shared app/console/config helpers
│   │   ├── cmd_config.py    # `sage config` subcommands: init, schema
│   │   ├── cmd_graph.py     # `sage graph` command
│   │   ├── cmd_index.py     # `sage index` command
│   │   └── cmd_search.py    # `sage search`, `sage status`, `sage list-kbs`
│   ├── mcp_server.py   # FastMCP: search_kb, list_knowledge_bases (lazy init)
│   └── templates/      # Jinja2 templates for --markdown output
│       ├── blockquote.md.j2  # Default: chunks as blockquotes under ### headings
│       └── table.md.j2       # Compact markdown table with truncated excerpts
├── config.yaml         # KB paths, embedding backend, Qdrant settings
├── config-example.yaml # Template — copy to config.yaml
├── pyproject.toml      # Hatch build; Python 3.11 pinned; ruff + pyright dev deps
├── pipeline_cache/     # Per-KB hash cache (gitignored) — enables incremental index
├── .qdrant/            # Qdrant local storage (gitignored)
└── .env                # OPENAI_API_KEY (gitignored — never commit)
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| Add / configure a KB | `config.yaml` → `knowledge_bases:` | Then `sage index --kb <name>` |
| Add KB-level tags | `config.yaml` → `knowledge_bases[].tags` | Used for `filter_kb_tags` in search/MCP |
| Change embedding model | `config.yaml` → `embedding:` | Provider: openai / ollama / litellm; `--force` re-index after switch |
| File chunking logic | `parsing.py` → `parse_nodes()` | `.md` → MarkdownNodeParser; code → CodeSplitter; fallback → SentenceSplitter |
| Frontmatter → metadata | `parsing.py` → `load_document()` | Only `.md` files; values cast to `str`; `tags` → `doc_tags` list |
| Cache invalidation | `pipeline_cache/<kb>/hashes.json` | v2: `{hash, mtime, size}`; v1: plain hash string (auto-upgraded) |
| Why a file skipped re-index | `indexer.py` → `index_kb()` | Stat fast-path first, then hash check |
| Embedding provider switching | `embeddings.py` → `make_embed_model()` | Centralised factory; replaces old `build_embed_model()` in indexer |
| MCP tool schemas | `mcp_server.py` | `filter_type`, `filter_status`, `filter_kb_tags`, `filter_doc_tags` |
| Metadata filter support | `searcher.py` → `search()` | Arbitrary `key=value` pairs + `kb_tags`/`doc_tags` OR-list filters |
| CLI commands | `sage_mcp/cli/` | `index`, `status`, `search`, `list-kbs`, `graph`, `config init`, `config schema` |
| Graph export | `graph.py` + `cli/cmd_graph.py` | File-level cosine similarity from existing embeddings; JSON/GraphML/DOT |
| Markdown output templates | `sage_mcp/templates/` | Jinja2 `.md.j2` files; pass built-in name or file path via `--template` |
| XDG-compliant paths | `settings.py` → `resolve_*()` helpers | Config, cache, Qdrant data dirs follow XDG spec |

## Code Map

| Symbol | File | Role |
|--------|------|------|
| `Config`, `KnowledgeBase`, `EmbeddingSettings`, `QdrantSettings`, `SearchSettings` | `settings.py` | Pydantic models; `load_config()` reads YAML |
| `env` | `settings.py` | Module-level `Env` singleton — imported by cli + mcp_server |
| `resolve_config_path()` | `settings.py` | CWD/config.yaml if exists, else `~/.config/sage-mcp/config.yaml` |
| `resolve_cache_dir()` | `settings.py` | `~/.cache/sage-mcp/pipeline_cache` |
| `resolve_data_dir()` | `settings.py` | `~/.local/share/sage-mcp/qdrant` |
| `make_embed_model()` | `embeddings.py` | Factory: returns `BaseEmbedding` for openai / ollama / litellm |
| `load_document()` | `parsing.py` | Path → `Document`; handles frontmatter + wikilinks for `.md` |
| `parse_nodes()` | `parsing.py` | `Document` → `list[BaseNode]`; routes by extension |
| `_cap_nodes()` | `parsing.py` | Secondary chunking pass for oversized MarkdownNodeParser nodes |
| `make_qdrant_client()` | `store.py` | Returns local (`path=`) or remote (`host=`) QdrantClient; path defaults to XDG data dir |
| `index_kb()` | `indexer.py` | Full ingestion loop; parallel embedding via `ThreadPoolExecutor`; returns `(indexed, skipped, pruned)` |
| `kb_status()` | `indexer.py` | Diff KB files vs cache without embedding — used by `status` command |
| `collect_files()` | `indexer.py` | Parallel dir walk with extension + exclude-pattern filtering |
| `KBStatus` | `indexer.py` | Dataclass: `never_indexed`, `unchanged`, `modified`, `new`, `deleted` |
| `search()` | `searcher.py` | Returns `(list[SearchResult], int)`; deduplicates by `(file_path, text)`, keeping highest score |
| `SearchResult` | `searcher.py` | Dataclass: `score`, `file_path`, `kb`, `text`, `metadata` |
| `build_file_similarity_graph()` | `graph.py` | Reads Qdrant vectors, mean-pools per file, computes pairwise cosine similarity |
| `to_json()` / `to_graphml()` / `to_dot()` | `graph.py` | Serialize edge list to JSON / GraphML / DOT format |
| `app` | `sage_mcp/cli/__init__.py` | Typer root; all imports deferred inside commands (fast startup) |
| `config_app` | `sage_mcp/cli/_common.py` | Typer sub-app for `sage config` subcommands |
| `main()` | `mcp_server.py` | Entry point; parses `--config` arg, calls `mcp.run()` |
| `mcp` | `mcp_server.py` | FastMCP instance; `_init()` lazy-loads config+client+embed on first call |

## Key Design Decisions

- **Hash cache v1→v2:** Cache entries upgraded from plain hash strings to `{hash, mtime, size}` dicts transparently. Stat fast-path skips content read when mtime+size unchanged.
- **Parser routing:** `.md` → `MarkdownNodeParser` (header splits) → `_cap_nodes` for oversized chunks. Code extensions → `CodeSplitter` (tree-sitter, 60 lines/10 overlap) with silent `Exception` fallback to `SentenceSplitter`. Unknown → `SentenceSplitter`.
- **Frontmatter as payload:** YAML frontmatter stripped before embedding; stored as Qdrant payload fields for filtered search. All values cast to `str`. Special key `tags` is normalised to `doc_tags` (list).
- **Wikilinks resolved:** `[[pihole]]` and `[[pihole|Pi-hole]]` → plain text before embedding.
- **Parallel walk + embed:** 16-thread `ThreadPoolExecutor` BFS for filesystem walk; separate `ThreadPoolExecutor` (default 4 workers) in `index_kb()` for parallel embedding. Shared state protected by `threading.Lock`.
- **Embeddings factory:** `embeddings.py` → `make_embed_model()` centralises provider construction (openai / ollama / litellm). Indexer and MCP server both import from here; the old `build_embed_model()` in indexer is removed.
- **KB tags + doc tags:** Each KB can declare `tags: [work, homelab]` in config. These are stored as `kb_tags` on every indexed node. Frontmatter `tags` field is normalised to `doc_tags` list. Both axes are filterable via `search()` and the MCP `search_kb` tool.
- **XDG-compliant paths:** Config, cache, and Qdrant data dirs resolve via `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` / `XDG_DATA_HOME` (falling back to `~/.config`, `~/.cache`, `~/.local/share`). CWD/config.yaml still takes precedence for config (backward compat).
- **CWD-relative paths (legacy):** CLI still falls back to CWD for config if no XDG path exists. MCP server uses `resolve_config_path()` then explicit `--config`.
- **MCP lazy init:** `_cfg`, `_client`, `_embed` are module globals initialized on first tool call via `_init()`. API key is only required when provider is `openai`. Config existence validated at init time with clear `RuntimeError` messages.
- **Search deduplication:** Hybrid retrieval (dense + BM25) can return the same chunk multiple times with different internal node IDs. Results are deduplicated by `(file_path, text)` key, keeping the highest score. The count of removed duplicates is returned alongside results.
- **Markdown output via Jinja2:** `--markdown` renders results through a `.md.j2` template. Built-ins ship in `sage_mcp/templates/`; custom templates are resolved by file path. Each result exposes `text` (raw) and `text_safe` (newlines→spaces, pipes escaped) for table-safe rendering. Output goes to stdout via `print()`, not `console.print()`, to avoid Rich word-wrapping on file redirect.
- **Graph export:** `sage graph` reads existing Qdrant vectors without re-embedding. Mean-pools chunk vectors per file to get file-level embeddings, then computes pairwise cosine similarity. Edges filtered by `--threshold` or pruned to `--top-k` neighbours per node. Optional dep group `[graph]` (`numpy`, `networkx`).

## Conventions

- Python **3.11 only** (`>=3.11,<3.12`) — use 3.11 syntax freely (`X | Y`, `match`, etc.)
- Line length **100** (ruff `line-length = 100`)
- Ruff lint rules: `E`, `F`, `I` (isort), `UP` (pyupgrade)
- Type checking: **pyright** (not mypy) — no mypy config present
- Build: **Hatch** (`hatchling`) — `pyproject.toml` only, no `setup.cfg`
- No test suite present. No CI config.
- Deferred imports inside CLI command functions — keeps `sage-mcp --help` fast
- **After every file edit run `ruff check --fix <file>` and resolve any remaining warnings before moving on**

## Anti-Patterns (This Project)

- Do **not** use `docstore.json` as the cache filename — actual file is `hashes.json`
- Do **not** read `pipeline_cache` as a docstore — it is a simple JSON hash dict, not a LlamaIndex storage
- Do **not** add `--config` default to an installed path — config is CWD-relative or XDG; never a hardcoded install path
- `CodeSplitter` failure is intentionally silenced (`except Exception: pass`) — do not log or re-raise; fallback to `SentenceSplitter` is the contract
- `filter_type` and `filter_status` in MCP are hardcoded filter axes; `filter_kb_tags` and `filter_doc_tags` handle tag filtering; arbitrary filters go through CLI `--filter key=value`
- Do **not** use `console.print()` for `--markdown` or `--json` output — Rich wraps long lines at terminal width when redirecting to a file; use `print()` instead
- Do **not** deduplicate search results by `node.node.node_id` — the hybrid retriever assigns different IDs to dense and sparse results for the same chunk; deduplicate by `(file_path, text)` instead
- Do **not** call `build_embed_model()` from `indexer` — it no longer exists; use `make_embed_model()` from `embeddings.py`
- Do **not** hardcode `embed_model: OpenAIEmbedding` type annotations — use `BaseEmbedding` (all providers share this interface)

## Commands

```bash
# Install (dev)
uv venv && source .venv/bin/activate
uv pip install -e ".[mcp,dev]"

# Install with optional extras
uv pip install -e ".[graph]"    # graph export (numpy, networkx)
uv pip install -e ".[litellm]"  # litellm embedding provider

# Config
sage config init                  # interactive wizard → XDG config path
sage config init --template       # write commented template without prompts
sage config init -o ./config.yaml # write to specific path
sage config schema                # print JSON Schema for config.yaml

# Index
sage index                    # all KBs
sage index --kb homelab       # single KB
sage index --force            # full re-embed (e.g. after model switch)

# Status (diff without embedding)
sage status
sage status --kb homelab

# Search
sage search "pihole DNS"
sage search "storage" --filter type=lxc --filter status=running
sage search "pihole" --json | jq '.results[].file_path'
sage search "pihole" --no-hybrid              # dense-only
sage search "pihole" --markdown               # blockquote template (default)
sage search "pihole" -m -t table              # table template
sage search "pihole" -m -t table -e 300       # table with longer excerpts
sage search "pihole" -m -t table -e 0         # table, no truncation
sage search "pihole" -m -t ~/my.md.j2         # custom template

# Graph export (requires [graph] extra)
sage graph                                    # JSON to stdout, top-1 edge per node
sage graph --kb homelab --format graphml -o out.graphml
sage graph --threshold 0.8 --top-k 0         # threshold mode (no top-k pruning)

# List configured KBs
sage list-kbs

# MCP server
sage-mcp-mcp                                      # config from CWD or XDG default
sage-mcp-mcp --config /path/to/config.yaml        # explicit config path
```

## MCP Tools

| Tool | Args | Returns |
|------|------|---------|
| `search_kb` | `query`, `kb?`, `top_k?`, `filter_type?`, `filter_status?`, `filter_kb_tags?`, `filter_doc_tags?` | `{results: [{score, file_path, kb, text, metadata}], duplicates_removed: N}` |
| `list_knowledge_bases` | — | `list[{name, path, description, extensions}]` |

`filter_kb_tags` and `filter_doc_tags` accept comma-separated values and apply OR logic (any matching tag passes).

## Markdown Template Variables

Available in all `.md.j2` templates:

| Variable | Type | Description |
|----------|------|-------------|
| `query` | `str` | The search query |
| `results` | `list[dict]` | Each entry: `score`, `file_path`, `kb`, `text`, `text_safe`, `metadata` |
| `duplicates_removed` | `int` | Duplicate chunks filtered out |
| `excerpt_length` | `int` | Max excerpt chars from `--excerpt-length` (0 = unlimited) |

`text_safe`: newlines collapsed to spaces, pipe characters escaped — safe for table cells. Use `text` for blockquote or fenced-code rendering.

## Notes / Gotchas

- `requested-features.md` — roadmap of planned work (PDF support, litellm/Bedrock, re-ranker, timing display, logging, SKILL.md, Qdrant server migration, XDG config, stale rows)
- Switching embedding models requires `--force` re-index; Qdrant collection must be recreated (vector dims differ per model)
- `VECTOR_DIMS` map in `indexer.py` exists but is not currently used for collection bootstrap — Qdrant auto-detects on first insert
- MCP `filter_type` / `filter_status` only cover two frontmatter axes; richer filtering requires CLI `--filter` or tag-based `filter_kb_tags`/`filter_doc_tags`
- Qdrant local storage uses a file lock — only one process can open `.qdrant/` at a time; running CLI while MCP server is active will fail with `AlreadyLocked`
- JSON output shape: `{results: [...], duplicates_removed: N}` — use `.results[].file_path` in jq
- litellm provider requires the `[litellm]` optional extra: `pip install 'sage-mcp[litellm]'`
- Graph export (`sage graph`) reads vectors already in Qdrant — no re-embedding needed, but requires the `[graph]` extra
- XDG path resolution: `QdrantSettings.path: null` (default) now resolves to `~/.local/share/sage-mcp/qdrant` instead of `.qdrant/` in CWD — existing local installs with a `.qdrant/` directory should set `path: .qdrant` in config to preserve behaviour
