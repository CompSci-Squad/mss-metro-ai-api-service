"""
Container de Injeção de Dependências para VIRAG-BIM.
Configura todos os services, clients e suas dependências.
"""

from dependency_injector import containers, providers

from app.clients.cache import RedisCache
from app.clients.opensearch import OpenSearchClient
from app.clients.s3 import S3Client
from app.core.settings import get_settings
from app.services.bim_analysis import BIMAnalysisService
from app.services.embedding_service import EmbeddingService
from app.services.ifc_processor import IFCProcessorService
from app.services.vlm_service import VLMService


class Container(containers.DeclarativeContainer):
    """Container de Injeção de Dependências."""

    wiring_config = containers.WiringConfiguration(
        modules=[
            "app.routes.bim.projects",
            "app.routes.bim.analysis",
            "app.routes.bim.progress",
            "app.routes.bim.comparison",
            "app.routes.bim.alerts",
            "app.routes.health",
        ]
    )

    # Settings
    settings = providers.Singleton(get_settings)

    # Clients
    redis_cache = providers.Singleton(
        RedisCache,
        host=settings.provided.redis_host,
        port=settings.provided.redis_port,
        ttl=settings.provided.cache_ttl,
    )

    opensearch_client = providers.Singleton(
        OpenSearchClient,
        hosts=settings.provided.opensearch_hosts,
    )

    s3_client = providers.Singleton(
        S3Client,
        bucket_name=settings.provided.s3_bucket,
        endpoint_url=settings.provided.s3_endpoint_url,
    )

    # ML Services
    vlm_service = providers.Singleton(
        VLMService,
        model_name=settings.provided.vlm_model_name,
        device=settings.provided.device,
        use_quantization=settings.provided.use_quantization,
    )

    embedding_service = providers.Singleton(
        EmbeddingService,
        model_name=settings.provided.embedding_model_name,
        device=settings.provided.device,
        cache=redis_cache,
    )

    # BIM Services
    ifc_processor = providers.Singleton(
        IFCProcessorService,
        embedding_service=embedding_service,
    )

    bim_analysis_service = providers.Singleton(
        BIMAnalysisService,
        vlm_service=vlm_service,
        embedding_service=embedding_service,
    )
