import re
from pathlib import Path

import yaml
from llama_index.core import Document
from llama_index.core.node_parser import CodeSplitter, MarkdownNodeParser
from llama_index.core.schema import BaseNode

CODE_LANGUAGE_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def extract_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    metadata = yaml.safe_load(match.group(1)) or {}
    body = text[match.end():]
    return metadata, body


def resolve_wikilinks(text: str) -> str:
    return re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)


def load_document(path: Path, kb_name: str) -> Document:
    raw = path.read_text(encoding="utf-8", errors="replace")
    ext = path.suffix.lower()

    if ext == ".md":
        frontmatter, body = extract_frontmatter(raw)
        body = resolve_wikilinks(body)
        metadata = {
            "kb": kb_name,
            "file_path": str(path),
            "file_name": path.name,
            "extension": ext,
            **{
                k: (v if isinstance(v, list) else str(v))
                for k, v in frontmatter.items()
                if v is not None
            },
        }
        return Document(text=body, metadata=metadata, id_=str(path))
    else:
        return Document(
            text=raw,
            metadata={
                "kb": kb_name,
                "file_path": str(path),
                "file_name": path.name,
                "extension": ext,
            },
            id_=str(path),
        )


_CHUNK_SIZE = 512
_CHUNK_OVERLAP = 64
_CHARS_PER_TOKEN = 4


def _cap_nodes(nodes: list[BaseNode], splitter) -> list[BaseNode]:
    out = []
    for node in nodes:
        if len(node.get_content()) > _CHUNK_SIZE * _CHARS_PER_TOKEN:
            subdoc = Document(text=node.get_content(), metadata=node.metadata)
            out.extend(splitter.get_nodes_from_documents([subdoc]))
        else:
            out.append(node)
    return out


def parse_nodes(doc: Document) -> tuple[list[BaseNode], bool]:
    """Parse a document into nodes. Returns (nodes, fell_back) where fell_back is True
    when CodeSplitter failed and SentenceSplitter was used as a fallback."""
    from llama_index.core.node_parser import SentenceSplitter

    size_capper = SentenceSplitter(chunk_size=_CHUNK_SIZE, chunk_overlap=_CHUNK_OVERLAP)
    ext = doc.metadata.get("extension", ".md")

    if ext == ".md":
        nodes = MarkdownNodeParser().get_nodes_from_documents([doc])
        return _cap_nodes(nodes, size_capper), False

    lang = CODE_LANGUAGE_MAP.get(ext)
    if lang:
        try:
            splitter = CodeSplitter(
                language=lang,
                chunk_lines=60,
                chunk_lines_overlap=10,
            )
            return splitter.get_nodes_from_documents([doc]), False
        except Exception:
            return size_capper.get_nodes_from_documents([doc]), True

    return size_capper.get_nodes_from_documents([doc]), False
