"""Decorators para cache Redis."""

import functools
import hashlib
import json
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


def cache_result(ttl: int = 3600, key_prefix: str = ""):
    """
    Decorator para cachear resultados de funções assíncronas no Redis.

    Args:
        ttl: Tempo de vida do cache em segundos (default: 1 hora)
        key_prefix: Prefixo para a chave do cache

    Usage:
        @cache_result(ttl=1800, key_prefix="project")
        async def get_project(project_id: str):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Gera chave de cache baseada nos argumentos
            cache_key = _generate_cache_key(func.__name__, key_prefix, args, kwargs)

            try:
                # Tenta buscar do cache (síncrono)
                from app.clients.cache import get_json

                cached = get_json(cache_key)
                if cached is not None:
                    logger.debug("cache_hit", key=cache_key, function=func.__name__)
                    return cached
            except Exception as e:
                logger.warning("cache_read_error", error=str(e), key=cache_key)

            # Executa função original
            result = await func(*args, **kwargs)

            try:
                # Salva no cache (síncrono)
                from app.clients.cache import set_json

                if result is not None:
                    set_json(cache_key, result, ttl)
                    logger.debug("cache_set", key=cache_key, ttl=ttl, function=func.__name__)
            except Exception as e:
                logger.warning("cache_write_error", error=str(e), key=cache_key)

            return result

        return wrapper

    return decorator


def _generate_cache_key(func_name: str, prefix: str, args: tuple, kwargs: dict) -> str:
    """
    Gera chave de cache determinística baseada em argumentos.

    Args:
        func_name: Nome da função
        prefix: Prefixo customizado
        args: Argumentos posicionais
        kwargs: Argumentos nomeados

    Returns:
        Chave de cache única
    """
    # Remove 'self' dos args se for método de classe
    clean_args = args[1:] if args and hasattr(args[0], "__dict__") else args

    # Cria representação dos argumentos
    args_repr = {
        "args": [_serialize_arg(arg) for arg in clean_args],
        "kwargs": {k: _serialize_arg(v) for k, v in sorted(kwargs.items())},
    }

    # Gera hash MD5
    args_str = json.dumps(args_repr, sort_keys=True, default=str)
    args_hash = hashlib.md5(args_str.encode()).hexdigest()[:12]

    # Monta chave
    parts = [prefix, func_name, args_hash] if prefix else [func_name, args_hash]
    return ":".join(parts)


def _serialize_arg(arg: Any) -> Any:
    """
    Serializa argumento para JSON.

    Args:
        arg: Argumento a serializar

    Returns:
        Argumento serializado
    """
    if isinstance(arg, (str, int, float, bool, type(None))):
        return arg
    elif isinstance(arg, (list, tuple)):
        return [_serialize_arg(item) for item in arg]
    elif isinstance(arg, dict):
        return {k: _serialize_arg(v) for k, v in arg.items()}
    elif isinstance(arg, bytes):
        # Para bytes (como imagens), usa hash MD5
        return f"bytes:{hashlib.md5(arg).hexdigest()[:16]}"
    elif hasattr(arg, "__dict__"):
        # Para objetos, ignora (normalmente é 'self')
        return "obj"
    else:
        # Para outros tipos, usa string
        return str(arg)


def invalidate_cache_pattern(key_pattern: str):
    """
    Invalida cache por padrão de chave.

    Args:
        key_pattern: Padrão de chave (ex: "project:*")

    Usage:
        invalidate_cache_pattern("project:get_project:*")
    """
    try:
        from app.clients.cache import _get_client

        redis_client = _get_client()
        keys = redis_client.keys(key_pattern)
        if keys:
            redis_client.delete(*keys)
            logger.info("cache_invalidated", pattern=key_pattern, keys_deleted=len(keys))
    except Exception as e:
        logger.error("cache_invalidation_error", error=str(e), pattern=key_pattern)
