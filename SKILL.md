# sage-mcp — Agent Skill Reference

Hybrid semantic search (dense vectors + BM25) over local markdown/code knowledge bases. Indexes files into Qdrant via LlamaIndex. Exposed as a CLI (`sage`) and an MCP server (`sage-mcp-mcp`). Agents inside an MCP-capable host should prefer MCP tools — shared persistent connection, no subprocess overhead, no Qdrant file-lock risk.

---

## Agent Notes (Read First)

| Issue | Detail |
|-------|--------|
| **Qdrant single-connection lock** | Only one process can open local Qdrant storage at a time. If the MCP server is running, CLI calls will fail with `AlreadyLocked`. Use MCP tools when the server is active. |
| **Re-index required after** | Changing embedding model (`sage index --force`), adding new KBs, changing KB tags in config |
| **API key** | `OPENAI_API_KEY` in `.env` or env var. Not required for `litellm`/`ollama` providers. |
| **XDG paths** | Config: `~/.config/sage-mcp/config.yaml` · Cache: `~/.cache/sage-mcp/pipeline_cache/` · Qdrant: `~/.local/share/sage-mcp/qdrant/`. `CWD/config.yaml` takes precedence if it exists. |
| **No results ≠ error** | `sage search` exits 0 when there are no results. Check `results` array length. |
| **JSON output path** | `--json` shape is `{results: [...], duplicates_removed: N}`. Use `.results[].file_path`, not `.[].file_path`. |
| **MCP lazy init** | Config and Qdrant client are loaded on the first tool call, not at server start. `RuntimeError` on bad config or missing API key. |

---

## MCP Tools (Preferred for Agents)

### `search_kb`

```
search_kb(query, kb?, top_k?, filter_type?, filter_status?, filter_kb_tags?, filter_doc_tags?)
```

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `query` | `str` | required | Natural language search query |
| `kb` | `str \| None` | `None` | Limit to a specific KB name (exact match) |
| `top_k` | `int` | `10` | Number of results to return |
| `filter_type` | `str \| None` | `None` | Filter by frontmatter `type` field (e.g. `lxc`, `vm`) |
| `filter_status` | `str \| None` | `None` | Filter by frontmatter `status` field (e.g. `running`, `planned`) |
| `filter_kb_tags` | `str \| None` | `None` | Comma-separated KB-level tags, OR logic (e.g. `work,homelab`) |
| `filter_doc_tags` | `str \| None` | `None` | Comma-separated document frontmatter `tags:` values, OR logic |

**Return shape:**
```json
{
  "results": [
    {
      "score": 0.847,
      "file_path": "/home/user/notes/pihole.md",
      "kb": "homelab",
      "text": "Pi-hole is a DNS sinkhole...",
      "metadata": {"type": "lxc", "status": "running", "tags": "dns,networking"}
    }
  ],
  "duplicates_removed": 2
}
```

### `list_knowledge_bases`

```
list_knowledge_bases()
```

No arguments. Returns `list[dict]`:
```json
[
  {
    "name": "homelab",
    "path": "/home/user/homelab-notes",
    "description": "Homelab infrastructure docs",
    "extensions": [".md"]
  }
]
```

### MCP Server Startup

```bash
sage-mcp-mcp                                   # config from CWD/config.yaml or XDG default
sage-mcp-mcp --config /path/to/config.yaml     # explicit config path
```

---

## CLI: `sage search`

```bash
sage search <query> [OPTIONS]
```

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--config` | `-c` | `Path` | XDG/CWD auto | Path to config.yaml |
| `--kb` | — | `str` | `None` | Limit search to this KB name (exact match) |
| `--top-k` | `-n` | `int` | config `search.top_k` | Number of results |
| `--filter` | `-f` | `str` (repeatable) | `None` | `key=value` frontmatter filter; AND across multiple flags |
| `--no-hybrid` | — | flag | `False` | Dense-only search (disables BM25) |
| `--kb-tag` | `-G` | `str` (repeatable) | `None` | Filter by KB config tag; OR within flag |
| `--doc-tag` | `-T` | `str` (repeatable) | `None` | Filter by document frontmatter `tags:` field; OR within flag |
| `--json` | — | flag | `False` | Output as JSON (pipeline-safe, stdout) |
| `--markdown` | `-m` | flag | `False` | Output via Jinja2 template (stdout) |
| `--template` | `-t` | `str` | `blockquote` | Built-in name (`blockquote`, `table`) or path to `.j2` file |
| `--excerpt-length` | `-e` | `int` | `120` | Max chars for excerpt in table template (0 = unlimited) |

### Examples

```bash
# Basic search
sage search "pihole DNS"

# Limit to one KB
sage search "storage" --kb homelab

# Frontmatter filters (AND)
sage search "storage" --filter type=lxc --filter status=running

# KB tag filter (OR)
sage search "backup" --kb-tag homelab --kb-tag work

# Document tag filter
sage search "networking" --doc-tag dns --doc-tag firewall

# JSON output for scripting
sage search "pihole" --json | jq '.results[].file_path'

# Dense-only (no BM25)
sage search "pihole" --no-hybrid

# Markdown output — blockquote (default)
sage search "pihole" --markdown

# Markdown output — table with custom excerpt length
sage search "pihole" -m -t table -e 300

# Markdown output — no excerpt truncation
sage search "pihole" -m -t table -e 0

# Custom Jinja2 template
sage search "pihole" -m -t ~/my-template.md.j2
```

---

## CLI: `sage index`

```bash
sage index [OPTIONS]
```

| Flag | Short | Type | Default | Description |
|------|-------|------|---------|-------------|
| `--config` | `-c` | `Path` | XDG/CWD auto | Path to config.yaml |
| `--kb` | — | `str` | `None` | Index only this KB name |
| `--force` | `-f` | flag | `False` | Re-embed all files, ignoring hash cache |
| `--workers` | `-w` | `int` | `4` | Parallel embedding workers |
| `--num-threads` | `-j` | `int` | `16` | Threads for filesystem walk |

```bash
sage index                        # all KBs
sage index --kb homelab           # single KB
sage index --force                # full re-embed (required after model change)
sage index --kb homelab --force   # force single KB
```

---

## CLI: Other Commands

| Command | Description |
|---------|-------------|
| `sage status [--kb NAME]` | Diff KB files vs index cache (unchanged / modified / new / deleted). No embedding. |
| `sage list-kbs [--json]` | List all configured KBs with name, path, extensions, description. |
| `sage config schema [-o FILE]` | Print JSON Schema for config.yaml to stdout or file. |
| `sage config init [--template] [--force] [-o PATH]` | Create config.yaml interactively (TTY) or write commented template (non-TTY / `--template`). |
| `sage graph [OPTIONS]` | Build file-level semantic similarity graph from Qdrant embeddings. Formats: `json`, `graphml`, `dot`. Requires `pip install -e ".[graph]"`. |

---

## Output Formats

### Default (Rich table)
Rendered to terminal with color and borders. Not pipeline-safe — Rich wraps lines at terminal width. Do not redirect to file.

### `--json`
Pipeline-safe. Written to stdout via `print()` (not Rich). Exact shape:
```json
{
  "results": [
    {
      "score": 0.847,
      "file_path": "/absolute/path/to/file.md",
      "kb": "homelab",
      "text": "raw chunk text",
      "metadata": {"type": "lxc", "status": "running"}
    }
  ],
  "duplicates_removed": 2
}
```

### `--markdown` / `-m`
Jinja2 template rendered to stdout via `print()`. Pipeline-safe.

| Built-in | Flag | Description |
|----------|------|-------------|
| `blockquote` | `-t blockquote` (default) | Chunks as blockquotes under `###` headings with file path |
| `table` | `-t table` | Compact markdown table; excerpts truncated to `--excerpt-length` |
| custom | `-t path/to/file.j2` | Any `.j2` file; resolved by filesystem path |

**Template variables:**

| Variable | Type | Description |
|----------|------|-------------|
| `query` | `str` | The search query |
| `results` | `list[dict]` | Each: `score`, `file_path`, `kb`, `text`, `text_safe`, `metadata` |
| `duplicates_removed` | `int` | Duplicate chunks filtered out |
| `excerpt_length` | `int` | Value of `--excerpt-length` |

`text_safe`: newlines → spaces, pipes escaped. Use for table cells. Use `text` for blockquote/fenced-code.

---

## Filtering Semantics

| Flag / Arg | Axis | Logic | Notes |
|-----------|------|-------|-------|
| `--kb` / `kb` | KB name | exact match | single value; CLI and MCP |
| `--filter key=value` | any frontmatter field | AND across multiple flags | CLI only; arbitrary keys |
| `filter_type` | frontmatter `type` field | exact match | MCP only; shorthand for `--filter type=value` |
| `filter_status` | frontmatter `status` field | exact match | MCP only; shorthand for `--filter status=value` |
| `--kb-tag` / `filter_kb_tags` | KB config `tags:` list | OR within flag, AND with other axes | CLI repeatable; MCP comma-separated |
| `--doc-tag` / `filter_doc_tags` | document frontmatter `tags:` field | OR within flag, AND with other axes | CLI repeatable; MCP comma-separated |

---

## Config Schema

```yaml
knowledge_bases:
  - name: homelab          # used in --kb / kb arg
    path: ~/homelab-notes  # absolute or ~ path
    description: ""
    tags: [homelab]        # used in --kb-tag / filter_kb_tags
    include_extensions: [.md]
    exclude_patterns: []

embedding:
  provider: openai         # openai | ollama | litellm
  model: text-embedding-3-small
  base_url: null           # override for Ollama: http://localhost:11434

qdrant:
  mode: local              # local | server
  path: null               # default: ~/.local/share/sage-mcp/qdrant
  collection: kb
  host: localhost          # server mode only
  port: 6333               # server mode only

search:
  top_k: 10                # default for --top-k / top_k
  hybrid: true             # false = dense-only; overridden by --no-hybrid
```

| Field | Used by |
|-------|---------|
| `knowledge_bases[].name` | `--kb`, `kb` arg |
| `knowledge_bases[].tags` | `--kb-tag`, `filter_kb_tags` |
| `embedding.provider` | determines if `OPENAI_API_KEY` is required |
| `qdrant.collection` | Qdrant collection name for all operations |
| `search.top_k` | default result count when `--top-k` / `top_k` not specified |
| `search.hybrid` | default hybrid mode; `--no-hybrid` overrides to `False` |
