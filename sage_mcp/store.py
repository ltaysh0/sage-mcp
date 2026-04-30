from qdrant_client import QdrantClient

from sage_mcp.settings import QdrantSettings


def make_qdrant_client(settings: QdrantSettings) -> QdrantClient:
    if settings.mode == "local":
        from sage_mcp.settings import resolve_data_dir
        path = settings.path or resolve_data_dir()
        return QdrantClient(path=str(path))
    return QdrantClient(host=settings.host, port=settings.port)
