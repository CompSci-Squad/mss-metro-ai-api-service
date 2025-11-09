"""
Health check endpoints para VIRAG-BIM.
Verifica status de todos os serviços externos.
"""

import time
from typing import Any

import structlog
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status
from opensearchpy import OpenSearch

from app.clients.cache import RedisCache
from app.core.container import Container
from app.core.settings import get_settings
from app.models.dynamodb import ConstructionAnalysisModel

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get(
    "/health",
    response_model=dict[str, Any],
    tags=["Saúde"],
    summary="Healthcheck básico",
    responses={
        200: {
            "description": "API está online",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "service": "VIRAG-BIM",
                        "timestamp": 1699459200.123
                    }
                }
            }
        }
    }
)
async def basic_health() -> dict[str, Any]:
    """Health check básico - verifica se API está online."""
    return {
        "status": "ok",
        "service": "VIRAG-BIM",
        "timestamp": time.time(),
    }


@router.get(
    "/health/detailed",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    tags=["Saúde"],
    summary="Healthcheck detalhado",
    description="""
    Verifica todos os serviços externos e dependências da aplicação.
    
    ## 🔍 Componentes Verificados
    
    1. **Redis**: Cache de resultados
    2. **S3/LocalStack**: Storage de arquivos (IFC, imagens)
    3. **DynamoDB**: Banco de dados NoSQL
    4. **OpenSearch**: Busca vetorial (embeddings)
    5. **ML Models**: Modelos VLM e CLIP carregados
    
    ## 📈 Status Possíveis
    
    - **healthy**: Serviço funcionando perfeitamente
    - **degraded**: Serviço funcionando parcialmente
    - **unhealthy**: Serviço indisponível
    - **unknown**: Status não pôde ser determinado
    
    ## ⏱️ Latência
    
    Cada serviço retorna `latency_ms` indicando tempo de resposta.
    
    ## 🚨 Alertas
    
    Se algum componente estiver unhealthy:
    - Status geral será "unhealthy"
    - Campo `error` detalha o problema
    
    ## 📝 Uso Sugerido
    
    - Dashboards de monitoramento
    - Alertas automáticos
    - Health checks de Kubernetes/Docker
    """,
    responses={
        200: {
            "description": "Health check detalhado executado",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "service": "VIRAG-BIM",
                        "timestamp": 1699459200.123,
                        "total_check_time_ms": 245.67,
                        "checks": {
                            "redis": {
                                "status": "healthy",
                                "latency_ms": 12.34
                            },
                            "s3": {
                                "status": "healthy",
                                "latency_ms": 45.67
                            },
                            "dynamodb": {
                                "status": "healthy",
                                "latency_ms": 89.12,
                                "tables_exist": True
                            },
                            "opensearch": {
                                "status": "healthy",
                                "latency_ms": 56.78,
                                "cluster_status": "green",
                                "nodes": 1
                            },
                            "ml_models": {
                                "status": "healthy",
                                "latency_ms": 41.76,
                                "vlm_loaded": True,
                                "embeddings_loaded": True,
                                "vlm_model": "Salesforce/blip2-opt-2.7b",
                                "embedding_model": "openai/clip-vit-base-patch32"
                            }
                        }
                    }
                }
            }
        },
        500: {
            "description": "Erro ao executar health check",
            "content": {
                "application/json": {
                    "example": {
                        "status": "unhealthy",
                        "checks": {
                            "redis": {
                                "status": "unhealthy",
                                "error": "Connection refused"
                            }
                        }
                    }
                }
            }
        }
    }
)
@inject
async def detailed_health(
    request: Request,
    redis_cache: RedisCache = Depends(Provide[Container.redis_cache]),
) -> dict[str, Any]:
    """
    Health check detalhado - verifica todos os serviços externos e ML models.

    Retorna status individual de cada componente:
    - Redis (cache)
    - DynamoDB (database - apenas Análises e Alertas)
    - OpenSearch (vector search)
    - ML Models (VLM + Embeddings)
    """
    start_time = time.time()
    settings = get_settings()

    checks = {
        "redis": {"status": "unknown", "latency_ms": None},
        "dynamodb": {"status": "unknown", "latency_ms": None},
        "opensearch": {"status": "unknown", "latency_ms": None},
        "ml_models": {"status": "unknown", "latency_ms": None},
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

    # Check DynamoDB
    try:
        dynamo_start = time.time()
        # Verifica se tabela de análises existe
        table_exists = ConstructionAnalysisModel.exists()
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

    # Check ML Models
    try:
        ml_start = time.time()
        
        # Verifica se modelos foram carregados no startup
        ml_models_loaded = getattr(request.app.state, "ml_models_loaded", False)
        vlm_service = getattr(request.app.state, "vlm_service", None)
        embedding_service = getattr(request.app.state, "embedding_service", None)
        
        if ml_models_loaded and vlm_service is not None and embedding_service is not None:
            checks["ml_models"] = {
                "status": "healthy",
                "latency_ms": round((time.time() - ml_start) * 1000, 2),
                "vlm_loaded": True,
                "embeddings_loaded": True,
                "vlm_model": getattr(vlm_service, "model_name", "unknown"),
                "embedding_model": getattr(embedding_service, "model_name", "unknown"),
            }
        else:
            checks["ml_models"] = {
                "status": "degraded",
                "latency_ms": round((time.time() - ml_start) * 1000, 2),
                "vlm_loaded": vlm_service is not None,
                "embeddings_loaded": embedding_service is not None,
                "message": "Models not fully loaded - analyses may be slow or fail",
            }
    except Exception as e:
        checks["ml_models"] = {
            "status": "unhealthy",
            "error": str(e),
        }
        logger.warning("ml_models_health_check_failed", error=str(e))

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
