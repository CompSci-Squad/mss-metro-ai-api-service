"""
Serviço de cache para resultados de análises usando Redis.
Evita reprocessamento de imagens similares/repetidas.
"""

import hashlib
import json

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class CacheService:
    """Serviço de cache para análises BIM."""

    def __init__(self, redis_client: Redis, ttl_seconds: int = 3600):
        self.redis = redis_client
        self.ttl = ttl_seconds

    def _generate_cache_key(self, project_id: str, image_hash: str) -> str:
        """Gera chave de cache baseada em projeto + hash da imagem."""
        return f"virag:analysis:{project_id}:{image_hash}"

    def _hash_image(self, image_bytes: bytes) -> str:
        """Gera hash SHA256 da imagem para identificação única."""
        return hashlib.sha256(image_bytes).hexdigest()

    async def get_cached_analysis(self, project_id: str, image_bytes: bytes) -> dict | None:
        """
        Busca análise em cache.

        Args:
            project_id: ID do projeto
            image_bytes: Bytes da imagem

        Returns:
            Resultado da análise se existir no cache, None caso contrário
        """
        try:
            image_hash = self._hash_image(image_bytes)
            cache_key = self._generate_cache_key(project_id, image_hash)

            cached_data = await self.redis.get(cache_key)

            if cached_data:
                logger.info("cache_hit", project_id=project_id, image_hash=image_hash[:16])
                return json.loads(cached_data)

            logger.info("cache_miss", project_id=project_id, image_hash=image_hash[:16])
            return None

        except Exception as e:
            logger.warning("erro_buscar_cache", error=str(e))
            return None

    async def cache_analysis(self, project_id: str, image_bytes: bytes, analysis_result: dict) -> bool:
        """
        Armazena análise em cache.

        Args:
            project_id: ID do projeto
            image_bytes: Bytes da imagem
            analysis_result: Resultado da análise

        Returns:
            True se cacheado com sucesso
        """
        try:
            image_hash = self._hash_image(image_bytes)
            cache_key = self._generate_cache_key(project_id, image_hash)

            # Serializa resultado
            cached_data = json.dumps(analysis_result)

            # Armazena com TTL
            await self.redis.setex(cache_key, self.ttl, cached_data)

            logger.info("cache_armazenado", project_id=project_id, image_hash=image_hash[:16], ttl=self.ttl)
            return True

        except Exception as e:
            logger.error("erro_armazenar_cache", error=str(e))
            return False

    async def invalidate_project_cache(self, project_id: str) -> int:
        """
        Invalida todo o cache de um projeto.

        Args:
            project_id: ID do projeto

        Returns:
            Número de chaves removidas
        """
        try:
            pattern = f"virag:analysis:{project_id}:*"
            keys = []

            # Busca todas as chaves do projeto
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                deleted = await self.redis.delete(*keys)
                logger.info("cache_invalidado", project_id=project_id, deleted_keys=deleted)
                return deleted

            return 0

        except Exception as e:
            logger.error("erro_invalidar_cache", error=str(e))
            return 0

    async def get_cache_stats(self) -> dict:
        """Retorna estatísticas do cache."""
        try:
            info = await self.redis.info("stats")

            return {
                "total_keys": await self.redis.dbsize(),
                "hits": info.get("keyspace_hits", 0),
                "misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0) / (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1)) * 100
                ),
            }

        except Exception as e:
            logger.error("erro_buscar_stats_cache", error=str(e))
            return {}
