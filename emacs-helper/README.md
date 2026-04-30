# sage.el

Emacs interface for [sage-mcp](../README.md) — search your knowledge bases from the minibuffer with live preview.

Results are presented via [consult](https://github.com/minad/consult) with live buffer preview and [marginalia](https://github.com/minad/marginalia) annotations showing KB name, score, and frontmatter `type`. No MCP connection or Docker required; calls the `sage` CLI directly as a subprocess.

## Dependencies

| Package | Min version | Source |
|---|---|---|
| Emacs | 28.1 | — |
| [consult](https://github.com/minad/consult) | 0.35 | MELPA |
| [marginalia](https://github.com/minad/marginalia) | 0.15 | MELPA |
| [transient](https://github.com/magit/transient) | 0.4.0 | built-in ≥ 29, MELPA otherwise |

The `sage` CLI must be on `PATH`, or its location set via `sage-cli-command`.

## Installation

### use-package (recommended)

```elisp
(use-package sage
  :load-path "~/path/to/kb-search/emacs-helper"
  :commands (sage-search sage-search-kb sage-index sage-dispatch)
  :custom
  (sage-config-file "~/path/to/kb-search/config.yaml")
  (sage-default-top-k 15)
  :bind
  ("C-c s s" . sage-search)
  ("C-c s k" . sage-search-kb)
  ("C-c s d" . sage-dispatch))
```

### Manual

```elisp
(add-to-list 'load-path "~/path/to/kb-search/emacs-helper")
(require 'sage)
```

## Commands

| Command | Description |
|---|---|
| `sage-search` | Search all configured KBs; prompts for query |
| `sage-search-kb` | Prompt for KB (with completion), then query |
| `sage-index` | Index all KBs; `C-u sage-index` forces full re-index |
| `sage-dispatch` | Transient menu — set CLI flags before searching or indexing |

### Transient menu (`sage-dispatch`)

```
Search options
  -n  Results          --top-k=       (default: sage-default-top-k)
  -H  Dense-only       --no-hybrid
  -t  Filter type      --filter-type=
  -s  Filter status    --filter-status=

Index options
  -F  Force re-index   --force

Common
  -k  Knowledge base   --kb=          (completion over configured KBs)
  -c  Config file      --config=      (file picker)

Search                   Other
  s  All KBs             i  Index
  k  In KB
```

## Configuration

```elisp
;; Path to config.yaml — nil means sage looks in its working directory
(setq sage-config-file "~/notes/sage/config.yaml")

;; Default number of results
(setq sage-default-top-k 10)

;; Sage executable — useful if sage isn't on PATH or you use a venv
(setq sage-cli-command "/home/user/code/kb-search/.venv/bin/sage")

;; Maximum file path display length in candidates
(setq sage-file-name-length-limit 80)
```

## Notes

- **Navigation**: results link back to source files. On selection, Emacs opens the file and jumps to the chunk using `search-forward` on the first line of the matched text. This is a best-effort match — it works reliably for prose and code but may land at the wrong occurrence if the same line appears multiple times.
- **Indexing output**: `sage-index` (and the transient `i` action) stream `sage index` output asynchronously to a `*sage-index*` buffer. Indexing can take a while on first run or after a model switch.
- **Qdrant file lock**: sage's embedded Qdrant holds a file lock on `.qdrant/`. If the sage MCP server is running concurrently, CLI searches from Emacs will fail. Stop the MCP server first, or point both at a remote Qdrant instance.
