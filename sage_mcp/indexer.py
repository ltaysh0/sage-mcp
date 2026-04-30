import fnmatch
import json
import os
import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor
from concurrent.futures import as_completed as _as_completed
from concurrent.futures import wait as _wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from sage_mcp.parsing import load_document, parse_nodes
from sage_mcp.settings import KnowledgeBase

# ---------------------------------------------------------------------------
# Cache helpers
#
# Cache entry format (v2): {"hash": str, "mtime": float, "size": int}
# Legacy format (v1):      plain hash string
#
# v1 entries are read-compatible — they just miss the stat fast-path and are
# transparently upgraded to v2 the next time that file is indexed.
# ---------------------------------------------------------------------------

def _make_entry(file_path: Path, doc_hash: str) -> dict[str, Any]:
    st = file_path.stat()
    return {"hash": doc_hash, "mtime": st.st_mtime, "size": st.st_size}


def _entry_hash(entry: Any) -> str | None:
    if isinstance(entry, dict):
        return entry.get("hash")
    return entry


def _stat_matches(entry: Any, st: os.stat_result) -> bool:
    if not isinstance(entry, dict):
        return False
    return entry.get("mtime") == st.st_mtime and entry.get("size") == st.st_size


VECTOR_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def _is_excluded(path: Path, kb_root: Path, patterns: list[str]) -> bool:
    """Return True if path matches any exclude pattern.

    Patterns are matched against both the filename alone and the path relative
    to the KB root, so both ``*.min.js`` and ``**/generated/*`` work as expected.
    ``**`` is supported because Python's fnmatch treats ``*`` as matching any
    character including path separators.
    """
    if not patterns:
        return False
    rel = str(path.relative_to(kb_root))
    name = path.name
    return any(
        fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat)
        for pat in patterns
    )


_WALK_WORKERS = 16


def _parallel_walk(
    kb: KnowledgeBase,
    on_file: Callable[[Path], None] | None = None,
    num_threads: int = _WALK_WORKERS,
) -> list[tuple[Path, os.DirEntry]]:
    exts = set(kb.include_extensions)
    kb_root = Path(kb.path)
    exclude = kb.exclude_patterns

    def scan_one(dir_path: str) -> tuple[list[tuple[Path, os.DirEntry]], list[str]]:
        matched: list[tuple[Path, os.DirEntry]] = []
        subdirs: list[str] = []
        try:
            with os.scandir(dir_path) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        subdirs.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        p = Path(entry.path)
                        if p.suffix.lower() in exts and not _is_excluded(p, kb_root, exclude):
                            matched.append((p, entry))
                            if on_file:
                                on_file(p)
        except PermissionError:
            pass
        return matched, subdirs

    results: list[tuple[Path, os.DirEntry]] = []
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        pending = {executor.submit(scan_one, str(kb_root))}
        while pending:
            done, not_done = _wait(pending, return_when=FIRST_COMPLETED)
            pending = set(not_done)
            for fut in done:
                matched, subdirs = fut.result()
                results.extend(matched)
                for d in subdirs:
                    pending.add(executor.submit(scan_one, d))
    return results


def collect_files(
    kb: KnowledgeBase,
    on_file: Callable[[Path], None] | None = None,
    num_threads: int = _WALK_WORKERS,
) -> list[Path]:
    return [p for p, _ in _parallel_walk(kb, on_file=on_file, num_threads=num_threads)]


@dataclass
class KBStatus:
    kb: KnowledgeBase
    never_indexed: bool
    unchanged: list[Path] = field(default_factory=list)
    modified: list[Path] = field(default_factory=list)
    new: list[Path] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


def kb_status(
    kb: KnowledgeBase,
    cache_dir: Path,
    on_walk: Callable[[Path], None] | None = None,
    on_check: Callable[[Path], None] | None = None,
    num_threads: int = _WALK_WORKERS,
) -> KBStatus:
    cache_file = cache_dir / kb.name / "hashes.json"

    if not cache_file.exists():
        files = collect_files(kb, num_threads=num_threads)
        return KBStatus(kb=kb, never_indexed=True, new=files)

    hash_cache: dict[str, Any] = json.loads(cache_file.read_text())
    walked = _parallel_walk(kb, on_file=on_walk, num_threads=num_threads)
    file_ids = set()
    status = KBStatus(kb=kb, never_indexed=False)

    for file_path, dir_entry in walked:
        doc_id = str(file_path)
        file_ids.add(doc_id)
        cached = hash_cache.get(doc_id)

        if cached is None:
            status.new.append(file_path)
        elif _stat_matches(cached, dir_entry.stat(follow_symlinks=False)):
            status.unchanged.append(file_path)
        else:
            doc = load_document(file_path, kb.name)
            if _entry_hash(cached) != doc.hash:
                status.modified.append(file_path)
            else:
                status.unchanged.append(file_path)

        if on_check:
            on_check(file_path)

    status.deleted = [p for p in hash_cache if p not in file_ids]
    return status


def index_kb(
    kb: KnowledgeBase,
    client: QdrantClient,
    embed_model: BaseEmbedding,
    collection: str,
    cache_dir: Path,
    *,
    force: bool = False,
    on_file: Callable[[Path, bool], None] | None = None,
    on_warning: Callable[[Path, str], None] | None = None,
    num_threads: int = _WALK_WORKERS,
    embed_workers: int = 4,
) -> tuple[int, int, int]:
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection,
        enable_hybrid=True,
        fastembed_sparse_model="Qdrant/bm25",
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    cache_file = cache_dir / kb.name / "hashes.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # Load the persisted cache regardless of --force so we can detect stale entries
    # even when the working cache is reset.
    old_cache: dict[str, Any] = json.loads(cache_file.read_text()) if cache_file.exists() else {}

    if force:
        hash_cache: dict[str, Any] = {}
    else:
        hash_cache = old_cache.copy()

    files = collect_files(kb, num_threads=num_threads)
    active_ids = {str(p) for p in files}

    # Prune against old_cache so that deleted files are cleaned up even on --force.
    stale_ids = [doc_id for doc_id in old_cache if doc_id not in active_ids]
    for doc_id in stale_ids:
        vector_store.delete(ref_doc_id=doc_id)
        if doc_id in hash_cache:
            del hash_cache[doc_id]
    pruned = len(stale_ids)

    lock = threading.Lock()
    indexed = 0
    skipped = 0

    def _process(file_path: Path) -> None:
        nonlocal indexed, skipped

        if not force:
            with lock:
                entry = hash_cache.get(str(file_path))
            if entry is not None and _stat_matches(entry, file_path.stat()):
                with lock:
                    skipped += 1
                    if on_file:
                        on_file(file_path, False)
                return

        doc = load_document(file_path, kb.name)

        if not force:
            with lock:
                cached_entry = hash_cache.get(doc.id_)
            if _entry_hash(cached_entry) == doc.hash:
                with lock:
                    hash_cache[doc.id_] = _make_entry(file_path, doc.hash)
                    skipped += 1
                    if on_file:
                        on_file(file_path, False)
                return

        nodes, fell_back = parse_nodes(doc)
        if fell_back and on_warning:
            with lock:
                on_warning(file_path, "CodeSplitter failed, using SentenceSplitter")

        kb_tags = kb.tags
        for node in nodes:
            node.metadata["kb_tags"] = kb_tags
            if "tags" in node.metadata:
                raw = node.metadata.pop("tags")
                if isinstance(raw, str):
                    node.metadata["doc_tags"] = [t.strip() for t in raw.split(",") if t.strip()]
                elif isinstance(raw, list):
                    node.metadata["doc_tags"] = [str(t) for t in raw]
                else:
                    node.metadata["doc_tags"] = []
            else:
                node.metadata["doc_tags"] = []

        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            embed_model=embed_model,
            show_progress=False,
        )

        with lock:
            hash_cache[doc.id_] = _make_entry(file_path, doc.hash)
            indexed += 1
            if on_file:
                on_file(file_path, True)

    with ThreadPoolExecutor(max_workers=embed_workers) as executor:
        futures = {executor.submit(_process, f): f for f in files}
        for future in _as_completed(futures):
            exc = future.exception()
            if exc is not None:
                fp = futures[future]
                if on_warning:
                    with lock:
                        on_warning(fp, f"Error during indexing: {exc}")

    cache_file.write_text(json.dumps(hash_cache, indent=2))
    return indexed, skipped, pruned
