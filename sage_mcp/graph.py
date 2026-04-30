import json
from pathlib import Path

import networkx as nx
import numpy as np
from qdrant_client import QdrantClient


def build_file_similarity_graph(
    client: QdrantClient,
    collection_name: str,
    kb_filter: str | None = None,
    threshold: float = 0.75,
    top_k: int | None = None,
) -> list[tuple[str, str, float]]:
    """Build a file-level semantic similarity graph from a Qdrant collection.

    Reads all vectors, groups by ``file_path`` payload, mean-pools per file,
    then computes pairwise cosine similarities.
    """
    file_vectors: dict[str, list] = {}
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            limit=1000,
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )

        for point in points:
            payload = point.payload or {}
            if kb_filter is not None and payload.get("kb") != kb_filter:
                continue
            file_path = payload.get("file_path")
            if file_path is None or point.vector is None:
                continue
            raw = point.vector
            if isinstance(raw, dict):
                # Hybrid collection: named vectors — pick the dense one.
                # LlamaIndex stores it as "text-dense"; fall back to the first
                # list value in case the name ever changes.
                vec = raw.get("text-dense")
                if not isinstance(vec, list):
                    vec = next((v for v in raw.values() if isinstance(v, list)), None)
            else:
                vec = raw
            if not isinstance(vec, list):
                continue
            file_vectors.setdefault(file_path, []).append(vec)

        if next_offset is None:
            break
        offset = next_offset

    if len(file_vectors) < 2:
        return []

    file_paths = list(file_vectors.keys())
    embeddings = np.array([np.mean(file_vectors[fp], axis=0) for fp in file_paths])

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = embeddings / norms
    sim_matrix = normalized @ normalized.T

    edges: list[tuple[str, str, float]] = []

    if top_k is not None:
        kept: set[tuple[str, str, float]] = set()
        n = len(file_paths)
        for i in range(n):
            sims = [(j, float(sim_matrix[i, j])) for j in range(n) if j != i]
            sims.sort(key=lambda x: x[1], reverse=True)
            for j, sim in sims[:top_k]:
                a, b = file_paths[i], file_paths[j]
                pair = tuple(sorted([a, b]))
                kept.add((pair[0], pair[1], sim))
        edges = list(kept)
    else:
        n = len(file_paths)
        for i in range(n):
            for j in range(i + 1, n):
                sim = float(sim_matrix[i, j])
                if sim >= threshold:
                    edges.append((file_paths[i], file_paths[j], sim))

    edges.sort(key=lambda x: x[2], reverse=True)
    return edges


def to_json(edges: list[tuple[str, str, float]], output_path: str | None = None) -> str:
    """Return adjacency-list JSON with nodes and edges."""
    nodes = [{"id": path} for path in sorted({n for e in edges for n in e[:2]})]
    edge_list = [{"source": s, "target": t, "weight": w} for s, t, w in edges]
    data = {"nodes": nodes, "edges": edge_list}
    text = json.dumps(data, indent=2)
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    return text


def to_graphml(edges: list[tuple[str, str, float]], output_path: str | None = None) -> str:
    """Return GraphML XML string."""
    G = nx.Graph()
    for src, tgt, weight in edges:
        G.add_edge(src, tgt, weight=weight)
    text = "".join(nx.generate_graphml(G))
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    return text


def _dot_id(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def to_dot(edges: list[tuple[str, str, float]], output_path: str | None = None) -> str:
    """Return GraphViz DOT string."""
    lines = ["graph G {"]
    for src, tgt, weight in edges:
        lines.append(f"  {_dot_id(src)} -- {_dot_id(tgt)} [weight={weight:.6f}];")
    lines.append("}")
    text = "\n".join(lines)
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
    return text
