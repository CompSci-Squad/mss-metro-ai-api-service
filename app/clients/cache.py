"""Redis cache - funções simples e classe para DI."""

import json
from typing import Any

import redis

from app.core.logger import logger
from app.core.settings import settings

# Cliente global
_redis_client = None


def _get_client() -> redis.Redis:
    """Retorna cliente Redis (singleton)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None,
            decode_responses=True,
        )
        logger.info("redis_connected")
    return _redis_client


class RedisCache:
    """Classe Redis para Dependency Injection."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0, ttl: int = 3600):
        self.host = host
        self.port = port
        self.db = db
        self.default_ttl = ttl
        self._client = None

    @property
    def client(self) -> redis.Redis:
        """Retorna cliente Redis (lazy loading)."""
        if self._client is None:
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
            )
            logger.info("redis_cache_connected", host=self.host, port=self.port)
        return self._client

    def get(self, key: str) -> str | None:
        """Busca valor no cache."""
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error("cache_get_error", key=key, error=str(e))
            return None

    def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Salva valor no cache."""
        try:
            self.client.setex(key, ttl or self.default_ttl, value)
            return True
        except Exception as e:
            logger.error("cache_set_error", key=key, error=str(e))
            return False

    def delete(self, key: str) -> bool:
        """Remove chave do cache."""
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error("cache_delete_error", key=key, error=str(e))
            return False

    def get_json(self, key: str) -> Any | None:
        """Busca e deserializa JSON."""
        value = self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Serializa e salva JSON."""
        try:
            return self.set(key, json.dumps(value), ttl)
        except (TypeError, ValueError):
            return False


def get(key: str) -> str | None:
    """Busca valor no cache."""
    try:
        return _get_client().get(key)
    except Exception as e:
        logger.error("cache_get_error", key=key, error=str(e))
        return None


def set(key: str, value: str, ttl: int = 3600) -> bool:
    """Salva valor no cache."""
    try:
        _get_client().setex(key, ttl, value)
        return True
    except Exception as e:
        logger.error("cache_set_error", key=key, error=str(e))
        return False


def delete(key: str) -> bool:
    """Remove chave do cache."""
    try:
        _get_client().delete(key)
        return True
    except Exception as e:
        logger.error("cache_delete_error", key=key, error=str(e))
        return False


def get_json(key: str) -> Any | None:
    """Busca e deserializa JSON."""
    value = get(key)
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def set_json(key: str, value: Any, ttl: int = 3600) -> bool:
    """Serializa e salva JSON."""
    try:
        return set(key, json.dumps(value), ttl)
    except (TypeError, ValueError):
        return False
