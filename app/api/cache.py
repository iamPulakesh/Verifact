import os
import json
import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "86400"))  # 24 hours default

_redis_client = None
_redis_available = False

def _get_redis():
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client if _redis_available else None

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        _redis_available = False
        _redis_client = False
        logger.info("[cache] No REDIS_URL set. Caching disabled.")
        return None

    try:
        import redis
        _redis_client = redis.from_url(redis_url, socket_connect_timeout=2, decode_responses=True)
        _redis_client.ping()
        _redis_available = True
        logger.info("[cache] Redis connected. Result caching enabled (TTL=%ds).", CACHE_TTL)
        return _redis_client
    except Exception as exc:
        logger.warning("[cache] Redis unavailable (%s). Caching disabled.", exc)
        _redis_available = False
        _redis_client = False
        return None


def _make_key(raw_input: str) -> str:
    normalized = raw_input.strip().lower()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"verifact:result:{digest}"


def _make_image_key(image_bytes: bytes) -> str:
    digest = hashlib.sha256(image_bytes).hexdigest()[:16]
    return f"verifact:result:img:{digest}"


def get_cached_result(raw_input: str) -> Optional[dict]:
    client = _get_redis()
    if not client:
        return None

    key = _make_key(raw_input)
    try:
        data = client.get(key)
        if data:
            logger.info("[cache] HIT for key %s", key)
            return json.loads(data)
    except Exception as exc:
        logger.warning("[cache] GET failed: %s", exc)
    return None


def set_cached_result(raw_input: str, result_dict: dict) -> None:
    client = _get_redis()
    if not client:
        return

    key = _make_key(raw_input)
    try:
        client.setex(key, CACHE_TTL, json.dumps(result_dict))
        logger.info("[cache] STORED key %s (TTL=%ds)", key, CACHE_TTL)
    except Exception as exc:
        logger.warning("[cache] SET failed: %s", exc)


def get_cached_image_result(image_bytes: bytes) -> Optional[dict]:
    client = _get_redis()
    if not client:
        return None

    key = _make_image_key(image_bytes)
    try:
        data = client.get(key)
        if data:
            logger.info("[cache] HIT for image key %s", key)
            return json.loads(data)
    except Exception as exc:
        logger.warning("[cache] GET failed: %s", exc)
    return None


def set_cached_image_result(image_bytes: bytes, result_dict: dict) -> None:
    client = _get_redis()
    if not client:
        return

    key = _make_image_key(image_bytes)
    try:
        client.setex(key, CACHE_TTL, json.dumps(result_dict))
        logger.info("[cache] STORED image key %s (TTL=%ds)", key, CACHE_TTL)
    except Exception as exc:
        logger.warning("[cache] SET failed: %s", exc)
