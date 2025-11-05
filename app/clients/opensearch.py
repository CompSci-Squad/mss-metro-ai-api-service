"""OpenSearch - funções simples para vector storage."""

from datetime import datetime
from typing import Any

from opensearchpy import OpenSearch

from app.core.logger import logger
from app.core.settings import settings

# Cliente global
_client = None
_index = settings.opensearch_index


def _get_client() -> OpenSearch:
    """Retorna cliente OpenSearch (singleton)."""
    global _client
    if _client is None:
        _client = OpenSearch(
            hosts=[{"host": settings.opensearch_host, "port": settings.opensearch_port}],
            http_auth=(settings.opensearch_user, settings.opensearch_password),
            use_ssl=settings.opensearch_use_ssl,
            verify_certs=settings.opensearch_verify_certs,
            ssl_show_warn=False,
        )
        _ensure_index()
        logger.info("opensearch_connected")
    return _client


def _ensure_index() -> None:
    """Cria índice se não existir."""
    if not _client.indices.exists(index=_index):
        _client.indices.create(
            index=_index,
            body={
                "settings": {"index": {"knn": True, "number_of_shards": 1}},
                "mappings": {
                    "properties": {
                        "project_id": {"type": "keyword"},
                        "image_id": {"type": "keyword"},
                        "s3_key": {"type": "keyword"},
                        "filename": {"type": "text"},
                        "upload_timestamp": {"type": "date"},
                        "sequence_number": {"type": "integer"},
                        "image_embedding": {
                            "type": "knn_vector",
                            "dimension": 512,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib",
                            },
                        },
                        "text_description": {"type": "text"},
                        "metadata": {"type": "object"},
                    }
                },
            },
        )


async def store_image(
    project_id: str,
    image_id: str,
    s3_key: str,
    filename: str,
    embedding: list[float],
    sequence_number: int,
    text_description: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Armazena embedding de imagem."""
    doc = {
        "project_id": project_id,
        "image_id": image_id,
        "s3_key": s3_key,
        "filename": filename,
        "upload_timestamp": datetime.utcnow().isoformat(),
        "sequence_number": sequence_number,
        "image_embedding": embedding,
        "text_description": text_description or "",
        "metadata": metadata or {},
    }

    response = _get_client().index(index=_index, id=image_id, body=doc)
    logger.info("image_stored", image_id=image_id)
    return response


async def search_similar(
    project_id: str,
    query_embedding: list[float],
    k: int = 10,
) -> list[dict[str, Any]]:
    """Busca imagens similares por embedding."""
    query = {
        "size": k,
        "query": {
            "bool": {
                "must": [{"term": {"project_id": project_id}}],
                "should": [
                    {
                        "knn": {
                            "image_embedding": {
                                "vector": query_embedding,
                                "k": k,
                            }
                        }
                    }
                ],
            }
        },
    }

    response = _get_client().search(index=_index, body=query)
    return [hit["_source"] for hit in response["hits"]["hits"]]


async def get_project_images(
    project_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Lista imagens de um projeto."""
    query = {
        "size": limit,
        "query": {"term": {"project_id": project_id}},
        "sort": [{"sequence_number": {"order": "asc"}}],
    }

    response = _get_client().search(index=_index, body=query)
    return [hit["_source"] for hit in response["hits"]["hits"]]


async def get_by_sequence(
    project_id: str,
    sequence_number: int,
) -> dict[str, Any] | None:
    """Busca imagem por número de sequência."""
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"project_id": project_id}},
                    {"term": {"sequence_number": sequence_number}},
                ]
            }
        }
    }

    response = _get_client().search(index=_index, body=query)
    hits = response["hits"]["hits"]
    return hits[0]["_source"] if hits else None
