# sage-mcp

Hybrid semantic search (dense vector + BM25) over local knowledge bases and codebases.

**Stack:** LlamaIndex · Qdrant (local embedded) · OpenAI or LiteLLM embeddings · FastMCP

## Setup

```bash
# Include MCP and LiteLLM features
uv tool install 'sage-mcp[mcp,litellm]'
```

uv will download Python 3.11 automatically if it's not already installed.

## Index

```bash
# Index all configured KBs
sage index

# Index one KB only
sage index --kb homelab

# Force full re-index (ignore cache)
sage index --force
```

## Status

```bash
# Diff KB files vs cache without embedding
sage status

# Single KB
sage status --kb homelab
```

## Search

```bash
# Hybrid search across all KBs
sage search "pihole DNS configuration"

# Limit to one KB
sage search "pihole" --kb homelab

# Filter by frontmatter fields
sage search "storage" --filter type=lxc --filter status=running

# More results
sage search "networking" --top-k 20

# Dense-only (no BM25)
sage search "pihole" --no-hybrid

# JSON output (for scripting / agent use)
sage search "pihole" --json

# Markdown output with full file paths (default template: blockquote)
sage search "pihole" --markdown

# Markdown table layout
sage search "pihole" --markdown --template table

# Custom Jinja2 template
sage search "pihole" --markdown --template ~/my-template.md.j2
```

### Markdown templates

The `--markdown` flag renders results via a [Jinja2](https://jinja.palletsprojects.com/) template.
Two built-in templates are included:

| Name | Description |
|------|-------------|
| `blockquote` | Each chunk indented as a blockquote under a `###` heading with full file path (default) |
| `table` | Compact markdown table with score, KB, full file path, and truncated excerpt |

To write a custom template, copy a built-in from `sage_mcp/templates/` and pass the file path via `--template`. The following variables are available:

| Variable | Type | Description |
|----------|------|-------------|
| `query` | `str` | The search query |
| `results` | `list[dict]` | Each entry has `score`, `file_path`, `kb`, `text`, `text_safe`, `metadata` |
| `duplicates_removed` | `int` | Number of duplicate chunks filtered out |

Each result's `text_safe` is the chunk text with newlines collapsed to spaces and pipe characters escaped — safe for use inside a Markdown table cell. Use `text` for blockquote or fenced-code rendering where the original formatting should be preserved.

## List KBs

```bash
sage list-kbs
```

## MCP (AI agent access)

Add to your MCP client config (use absolute paths):

```json
{
  "mcpServers": {
    "sage-mcp": {
      "command": "/path/to/sage-mcp/.venv/bin/sage-mcp",
      "args": ["--config", "/path/to/sage-mcp/config.yaml"]
    }
  }
}
```

The `--config` flag is optional; without it the server looks for `config.yaml` in its working directory.

Tools exposed:
- `search_kb(query, kb?, top_k?, filter_type?, filter_status?)` — returns `{results: [...], duplicates_removed: N}`
- `list_knowledge_bases()` — list configured KBs

## Config

Edit `config.yaml` to add KBs or switch the embedding backend. Use `config-example.yaml` as a template.

**Switching to Ollama** (once nomic-embed-text is running with GPU acceleration):

```yaml
embedding:
  provider: ollama
  model: nomic-embed-text
  base_url: http://<ollama-ip>:11434
```

Then `sage index --force` to re-embed everything.

## Incremental updates

The indexer tracks a content hash per file in `pipeline_cache/<kb-name>/hashes.json`.
Re-running `sage index` only re-embeds files that have changed. Safe to run on a cron or inotify watch.
