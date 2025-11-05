"""
Health check endpoints para VIRAG-BIM.
Verifica status de todos os serviços externos.
"""

import time
from typing import Any

import structlog
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, status
from opensearchpy import OpenSearch

from app.clients.cache import RedisCache
from app.clients.s3 import S3Client
from app.core.container import Container
from app.core.settings import get_settings
from app.models.dynamodb import BIMProject

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/health", response_model=dict[str, Any])
async def basic_health() -> dict[str, Any]:
    """Health check básico - apenas verifica se API está rodando."""
    return {
        "status": "ok",
        "service": "VIRAG-BIM",
        "timestamp": time.time(),
    }


@router.get("/health/detailed", response_model=dict[str, Any], status_code=status.HTTP_200_OK)
@inject
async def detailed_health(
    redis_cache: RedisCache = Depends(Provide[Container.redis_cache]),
    s3_client: S3Client = Depends(Provide[Container.s3_client]),
) -> dict[str, Any]:
    """
    Health check detalhado - verifica todos os serviços externos.

    Retorna status individual de cada componente:
    - Redis (cache)
    - S3/LocalStack (storage)
    - DynamoDB (database)
    - OpenSearch (vector search)
    """
    start_time = time.time()
    settings = get_settings()

    checks = {
        "redis": {"status": "unknown", "latency_ms": None},
        "s3": {"status": "unknown", "latency_ms": None},
        "dynamodb": {"status": "unknown", "latency_ms": None},
        "opensearch": {"status": "unknown", "latency_ms": None},
    }

    # Check Redis
    try:
        redis_start = time.time()
        await redis_cache.ping()
        checks["redis"] = {
            "status": "healthy",
            "latency_ms": round((time.time() - redis_start) * 1000, 2),
        }
    except Exception as e:
        checks["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        logger.warning("redis_health_check_failed", error=str(e))

    # Check S3
    try:
        s3_start = time.time()
        await s3_client.health_check()
        checks["s3"] = {
            "status": "healthy",
            "latency_ms": round((time.time() - s3_start) * 1000, 2),
        }
    except Exception as e:
        checks["s3"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        logger.warning("s3_health_check_failed", error=str(e))

    # Check DynamoDB
    try:
        dynamo_start = time.time()
        # Tenta verificar se tabela existe
        table_exists = BIMProject.exists()
        checks["dynamodb"] = {
            "status": "healthy" if table_exists else "degraded",
            "latency_ms": round((time.time() - dynamo_start) * 1000, 2),
            "tables_exist": table_exists,
        }
    except Exception as e:
        checks["dynamodb"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        logger.warning("dynamodb_health_check_failed", error=str(e))

    # Check OpenSearch
    try:
        os_start = time.time()
        os_client = OpenSearch(
            hosts=settings.opensearch_hosts,
            use_ssl=settings.opensearch_use_ssl,
            verify_certs=settings.opensearch_verify_certs,
        )
        cluster_health = os_client.cluster.health()
        checks["opensearch"] = {
            "status": "healthy" if cluster_health["status"] in ["green", "yellow"] else "degraded",
            "latency_ms": round((time.time() - os_start) * 1000, 2),
            "cluster_status": cluster_health["status"],
            "nodes": cluster_health["number_of_nodes"],
        }
    except Exception as e:
        checks["opensearch"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        logger.warning("opensearch_health_check_failed", error=str(e))

    # Status geral
    all_healthy = all(check["status"] == "healthy" for check in checks.values())
    any_degraded = any(check["status"] == "degraded" for check in checks.values())
    any_unhealthy = any(check["status"] == "unhealthy" for check in checks.values())

    if all_healthy:
        overall_status = "healthy"
    elif any_unhealthy:
        overall_status = "unhealthy"
    elif any_degraded:
        overall_status = "degraded"
    else:
        overall_status = "unknown"

    total_latency = round((time.time() - start_time) * 1000, 2)

    return {
        "status": overall_status,
        "service": "VIRAG-BIM",
        "timestamp": time.time(),
        "total_check_time_ms": total_latency,
        "checks": checks,
    }
