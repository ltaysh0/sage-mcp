# Tests

## Smoke tests (shell)

Shell-based integration tests that exercise the real `sage` CLI binary against a small fixture KB.
No mocking — these catch integration regressions at the binary level.

### Prerequisites

- Package installed: `uv pip install -e ".[mcp,dev]"`
- For indexing/search tests: `OPENAI_API_KEY` set in env or `.env`

### Run

```bash
bash tests/smoke.sh
```

Tests that require `OPENAI_API_KEY` are automatically skipped when the key is absent.
Each test run creates isolated temp dirs for Qdrant storage and cache — no CWD pollution.

### What is tested

| Group | Requires API key | Description |
|-------|-----------------|-------------|
| `test_help` | No | All `--help` flags exit 0 and contain expected keywords |
| `test_config_schema` | No | JSON Schema output is valid JSON with expected structure |
| `test_config_init_template` | No | Template writing, `--force` overwrite, refusal without `--force` |
| `test_list_kbs` | No | KB listing (table + JSON), field validation, bad config path |
| `test_status_no_index` | No | Status before indexing reports "never indexed"; unknown KB exits non-zero |
| `test_index` | Yes | Indexing, cache file creation, idempotency, `--workers`, `--force`, unknown KB |
| `test_search` | Yes | Search, `--json` shape, `--kb`, `--no-hybrid`, `--kb-tag`, `--doc-tag`, `--markdown`, templates, `-n`, no-results |
| `test_search_filters` | Yes | `--filter key=value`, multiple filters, bad filter rejection, combined flags |

### Fixture KB

```
tests/fixtures/kb/
├── alpha.md      # type: note, status: active, tags: [search, retrieval]
├── beta.md       # type: guide, status: draft, tags: [setup, configuration]
└── subdir/
    └── gamma.md  # type: note, status: active, tags: [search]
```

The fixture config (`tests/fixtures/config.yaml`) uses placeholder strings that are
substituted with absolute temp paths at runtime via `sed`.

### Isolation

- `QDRANT_DIR` — fresh `mktemp -d` per run; Qdrant local storage goes here
- `CACHE_DIR` — fresh `mktemp -d` per run; `XDG_CACHE_HOME` is overridden to point here
- Both are removed by a `trap EXIT` handler even if the script fails
- The real `~/.cache/sage-mcp` and `~/.local/share/sage-mcp` are never touched
