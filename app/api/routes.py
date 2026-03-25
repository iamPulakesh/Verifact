import os
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.api.rate_limit import limiter, LIMITS
from app.api.cache import (
    get_cached_result, set_cached_result,
    get_cached_image_result, set_cached_image_result,
)
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
MAX_IMAGE_BYTES = settings.MAX_FILE_SIZE

def _sanitize_error(msg: str) -> str:
    for secret in [
        settings.GROQ_API_KEY, settings.TAVILY_API_KEY,
        settings.PINECONE_API_KEY, settings.HF_TOKEN,
        settings.SAMBANOVA_API_KEY,
    ]:
        if secret:
            msg = msg.replace(secret, "***")
    return msg

PROVIDER_MODELS = {
    "groq": ["meta-llama/llama-4-scout-17b-16e-instruct", "openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3-32b", "moonshotai/kimi-k2-instruct", "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-safeguard-20b"],
    "sambanova": ["DeepSeek-R1-Distill-Llama-70B", "DeepSeek-V3-0324", "gpt-oss-120b", "Qwen3-235B", "Qwen3-32B", "DeepSeek-V3.1", "Meta-Llama-3.1-8B-Instruct", "Meta-Llama-3.3-70B-Instruct"],
    "cerebras": ["llama3.1-8b", "gpt-oss-120b"],
}

class ModelSwitchRequest(BaseModel):
    provider: str
    model: str

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in PROVIDER_MODELS:
            raise ValueError(f"Invalid provider. Must be one of: {list(PROVIDER_MODELS.keys())}")
        return v

@router.get("/model/current", tags=["model"])
async def get_current_model(request: Request):
    import app.config as cfg
    return {
        "provider": cfg.LLM_PROVIDER,
        "model": _get_active_model_name(cfg.LLM_PROVIDER),
        "providers": PROVIDER_MODELS,
    }

@router.post("/model/switch", tags=["model"])
@limiter.limit("20/minute")
async def switch_model(request: Request, body: ModelSwitchRequest):
    import app.config as cfg

    available = PROVIDER_MODELS.get(body.provider, [])
    if body.model not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{body.model}' not available for provider '{body.provider}'. Available: {available}",
        )

    cfg.LLM_PROVIDER = body.provider
    if body.provider == "groq":
        cfg.LLM_MODEL = body.model
    elif body.provider == "sambanova":
        cfg.SAMBANOVA_MODEL = body.model
    elif body.provider == "cerebras":
        cfg.CEREBRAS_MODEL = body.model

    logger.info("[route] Model switched to %s / %s", body.provider, body.model)
    return {"status": "ok", "provider": body.provider, "model": body.model}

def _get_active_model_name(provider: str) -> str:
    import app.config as cfg
    if provider == "sambanova":
        return cfg.SAMBANOVA_MODEL
    if provider == "cerebras":
        return cfg.CEREBRAS_MODEL
    return cfg.LLM_MODEL

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

    cached = get_cached_result(body.url)
    if cached:
        logger.info("[route] check_url CACHE HIT: %s", body.url[:80])
        return JSONResponse(content=cached)

    from app.agent.runner import run_fact_check
    logger.info("[route] check_url: %s", body.url[:80])
    try:
        verdict = run_fact_check(body.url)
        result = verdict.to_dict()
        set_cached_result(body.url, result)
        return JSONResponse(content=result)
    except Exception as exc:
        msg = _sanitize_error(str(exc))
        logger.error("[route] check_url failed: %s", msg)
        raise HTTPException(status_code=500, detail=msg)


@router.post("/check/text", tags=["fact-check"])
@limiter.limit(LIMITS["check"])
async def check_text(request: Request, body: CheckTextRequest):

    cached = get_cached_result(body.text)
    if cached:
        logger.info("[route] check_text CACHE HIT: %d chars", len(body.text))
        return JSONResponse(content=cached)

    from app.agent.runner import run_fact_check
    logger.info("[route] check_text: %d chars", len(body.text))
    try:
        verdict = run_fact_check(body.text)
        result = verdict.to_dict()
        set_cached_result(body.text, result)
        return JSONResponse(content=result)
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

    cached = get_cached_image_result(data)
    if cached:
        logger.info("[route] check_image CACHE HIT: %s", file.filename)
        return JSONResponse(content=cached)

    from app.agent.runner import run_fact_check
    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.flush()
        tmp.close()

        logger.info("[route] check_image: %s (%d bytes)", file.filename, len(data))
        verdict = run_fact_check(tmp.name)
        result = verdict.to_dict()
        set_cached_image_result(data, result)
        return JSONResponse(content=result)
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

