import os
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.api.rate_limit import limiter, LIMITS
from app.agent.runner import run_fact_check
import time
from app.rag.vectorstore import get_collection_stats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

class CheckUrlRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def must_be_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("url must not be empty")
        return v.strip()

class CheckTextRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def minimum_length(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("text must be at least 10 characters")
        return v.strip()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
MAX_IMAGE_BYTES = settings.MAX_FILE_SIZE  # 5 MB

def _sanitize_error(msg: str) -> str:
    for secret in [
        settings.GROQ_API_KEY, settings.TAVILY_API_KEY,
        settings.PINECONE_API_KEY, settings.HF_TOKEN,
        settings.GOOGLE_API_KEY, settings.SAMBANOVA_API_KEY,
    ]:
        if secret:
            msg = msg.replace(secret, "***")
    return msg

# Routes
@router.get("/health", tags=["system"])
@limiter.limit(LIMITS["health"])
async def health(request: Request):
    try:
        stats = get_collection_stats()
    except Exception:
        stats = {"ready": False, "total_documents": 0}

    return {
        "status": "ok",
        "provider": settings.LLM_PROVIDER,
        "rag_ready": stats.get("ready", False),
        "rag_docs": stats.get("total_documents", 0),
        "timestamp": int(time.time()),
    }


@router.post("/check/url", tags=["fact-check"])
@limiter.limit(LIMITS["check"])
async def check_url(request: Request, body: CheckUrlRequest):

    logger.info("[route] check_url: %s", body.url[:80])
    try:
        verdict = run_fact_check(body.url)
        return JSONResponse(content=verdict.to_dict())
    except Exception as exc:
        msg = _sanitize_error(str(exc))
        logger.error("[route] check_url failed: %s", msg)
        raise HTTPException(status_code=500, detail=msg)


@router.post("/check/text", tags=["fact-check"])
@limiter.limit(LIMITS["check"])
async def check_text(request: Request, body: CheckTextRequest):

    logger.info("[route] check_text: %d chars", len(body.text))
    try:
        verdict = run_fact_check(body.text)
        return JSONResponse(content=verdict.to_dict())
    except Exception as exc:
        msg = _sanitize_error(str(exc))
        logger.error("[route] check_text failed: %s", msg)
        raise HTTPException(status_code=500, detail=msg)


@router.post("/check/image", tags=["fact-check"])
@limiter.limit(LIMITS["image"])
async def check_image(request: Request, file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                f"Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}"
            ),
        )

    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // (1024 * 1024)} MB). Max: 5 MB.",
        )

    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()

        logger.info("[route] check_image: %s (%d bytes)", file.filename, len(data))
        verdict = run_fact_check(tmp.name)
        return JSONResponse(content=verdict.to_dict())
    except HTTPException:
        raise
    except Exception as exc:
        msg = _sanitize_error(str(exc))
        logger.error("[route] check_image failed: %s", msg)
        raise HTTPException(status_code=500, detail=msg)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
