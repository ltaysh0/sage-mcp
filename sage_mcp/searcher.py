from dataclasses import dataclass

from llama_index.core import VectorStoreIndex
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.vector_stores.types import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient


@dataclass
class SearchResult:
    score: float
    file_path: str
    kb: str
    text: str
    metadata: dict


def search(
    query: str,
    client: QdrantClient,
    embed_model: BaseEmbedding,
    collection: str,
    *,
    top_k: int = 10,
    hybrid: bool = True,
    kb_filter: str | None = None,
    metadata_filters: dict[str, str] | None = None,
    kb_tags: list[str] | None = None,
    doc_tags: list[str] | None = None,
) -> tuple[list[SearchResult], int]:
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection,
        enable_hybrid=hybrid,
        fastembed_sparse_model="Qdrant/bm25",
    )

    filters = []
    if kb_filter:
        filters.append(MetadataFilter(key="kb", value=kb_filter, operator=FilterOperator.EQ))
    if metadata_filters:
        for k, v in metadata_filters.items():
            filters.append(MetadataFilter(key=k, value=v, operator=FilterOperator.EQ))

    if kb_tags:
        tag_filters = [
            MetadataFilter(key="kb_tags", value=tag, operator=FilterOperator.EQ)
            for tag in kb_tags
        ]
        if len(tag_filters) == 1:
            filters.extend(tag_filters)
        else:
            filters.append(MetadataFilters(filters=tag_filters, condition=FilterCondition.OR))

    if doc_tags:
        tag_filters = [
            MetadataFilter(key="doc_tags", value=tag, operator=FilterOperator.EQ)
            for tag in doc_tags
        ]
        if len(tag_filters) == 1:
            filters.extend(tag_filters)
        else:
            filters.append(MetadataFilters(filters=tag_filters, condition=FilterCondition.OR))

    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
    retriever = index.as_retriever(
        similarity_top_k=top_k,
        filters=MetadataFilters(filters=filters) if filters else None,
    )

    nodes = retriever.retrieve(query)

    best: dict[tuple[str, str], object] = {}
    for node in nodes:
        key = (node.metadata.get("file_path", ""), node.text)
        if key not in best or (node.score or 0.0) > (best[key].score or 0.0):
            best[key] = node

    unique = sorted(best.values(), key=lambda n: n.score or 0.0, reverse=True)
    duplicates_removed = len(nodes) - len(unique)

    return [
        SearchResult(
            score=node.score or 0.0,
            file_path=node.metadata.get("file_path", ""),
            kb=node.metadata.get("kb", ""),
            text=node.text,
            metadata=node.metadata,
        )
        for node in unique
    ], duplicates_removed
