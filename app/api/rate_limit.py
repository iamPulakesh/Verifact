import os
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
import redis as _redis

logger = logging.getLogger(__name__)

LIMITS = {
    "health": "60/minute",    
    "check":  "10/minute",    
    "image":  "5/minute",    
}

def _resolve_storage_uri() -> str | None:

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return None

    try:
        client = _redis.from_url(redis_url, socket_connect_timeout=2)
        client.ping()
        logger.info("[rate_limit] Redis reachable at %s", redis_url)
        return redis_url
    except Exception as exc:
        logger.warning(
            "[rate_limit] Redis unreachable (%s). "
            "Falling back to in-memory storage.",
            exc,
        )
        return None


def _build_limiter() -> Limiter:
    storage_uri = _resolve_storage_uri()

    if storage_uri:
        logger.info("[rate_limit] Using Redis-backed limiter.")
        return Limiter(
            key_func=get_remote_address,
            storage_uri=storage_uri,
        )

    logger.info("[rate_limit] Using in-memory limiter (single-process only).")
    return Limiter(key_func=get_remote_address)

limiter: Limiter = _build_limiter()
