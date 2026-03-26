import os
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
import redis as _redis

logger = logging.getLogger(__name__)

LIMITS = {
    "check":  "5/hour",    
    "image":  "5/hour",    
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

def get_admin_aware_key(request) -> str | None:
    bypass_key = os.getenv("ADMIN_BYPASS_KEY")
    if bypass_key and request.headers.get("X-Admin-Bypass") == bypass_key:
        return None
    return get_remote_address(request)

def _build_limiter() -> Limiter:
    storage_uri = _resolve_storage_uri()
    
    limiter = Limiter(
        key_func=get_admin_aware_key,
        storage_uri=storage_uri if storage_uri else "memory://",
        headers_enabled=True,
    )
    
    return limiter

limiter: Limiter = _build_limiter()
