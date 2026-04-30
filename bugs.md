# Known Issues / Bugs

## Python file indexing appears to hang on first run

**Symptom:** `sage index` shows progress stuck at `4/13` (or similar) for several minutes when encountering the first `.py` file.

**Cause:** `tree-sitter-language-pack` downloads language parsers on first use. This one-time initialization can take 1–5 minutes depending on network speed.

**Workaround:** Simply wait — indexing completes normally on the second attempt once parsers are cached locally.

**File:** `sage_mcp/parsing.py`
**Dependency:** `tree-sitter-language-pack>=0.2`
