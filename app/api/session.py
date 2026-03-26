import json
import hashlib
import hmac
import base64
import os
import logging
from typing import Optional

from fastapi import Request, Response

logger = logging.getLogger(__name__)

_SECRET = os.getenv("SESSION_SECRET", "").strip()
if not _SECRET:
    _SECRET = hashlib.sha256(os.urandom(32)).hexdigest()
    logger.info("[session] No SESSION_SECRET set; using auto-generated key (resets on restart).")

COOKIE_NAME = "verifact_session"
COOKIE_MAX_AGE = 86400 * 7  


def _sign(payload: str) -> str:
    sig = hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    return sig


def _encode(data: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    sig = _sign(payload)
    return f"{sig}.{payload}"


def _decode(cookie_value: str) -> Optional[dict]:
    try:
        sig, payload = cookie_value.split(".", 1)
        if not hmac.compare_digest(sig, _sign(payload)):
            logger.warning("[session] Invalid cookie signature — ignoring.")
            return None
        return json.loads(base64.urlsafe_b64decode(payload).decode())
    except Exception:
        return None


def get_session_model(request: Request) -> Optional[dict]:

    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    data = _decode(cookie)
    if data and "provider" in data and "model" in data:
        return {"provider": data["provider"], "model": data["model"]}
    return None


_SECURE_COOKIES = os.getenv("SECURE_COOKIES", "true").strip().lower() == "true"

def set_session_model(response: Response, provider: str, model: str) -> None:
    data = {"provider": provider, "model": model}
    response.set_cookie(
        key=COOKIE_NAME,
        value=_encode(data),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="none",
        secure=_SECURE_COOKIES,
    )
    logger.info("[session] Set model preference: %s / %s", provider, model)

