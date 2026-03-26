import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
import warnings

warnings.filterwarnings("ignore", message="Unclosed client session")

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.api.rate_limit import limiter
from app.api.routes import router

class SensitiveDataFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        from app.config import settings
        import os
        raw_secrets = [
            settings.GROQ_API_KEY, settings.TAVILY_API_KEY,
            settings.PINECONE_API_KEY, settings.HF_TOKEN,
            settings.SAMBANOVA_API_KEY, settings.FIREWORKS_API_KEY,
            settings.CEREBRAS_API_KEY,
            os.getenv("GOOGLE_FACTCHECK_API_KEY", ""),
            os.getenv("SESSION_SECRET", ""),
        ]
        self.secrets = [s.strip() for s in raw_secrets if s and len(s) > 8]

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        scrubbed = False
        for secret in self.secrets:
            if secret in msg:
                msg = msg.replace(secret, "***REDACTED***")
                scrubbed = True
        if scrubbed:
            record.msg = msg
            record.args = ()
        return True

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
for handler in logging.root.handlers:
    handler.addFilter(SensitiveDataFilter())

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Verifact is starting..")
    logger.info("Pre-loading models into RAM...")
    from app.rag.vectorstore import get_embeddings
    get_embeddings()
    logger.info("Agent is Ready. Waiting for Requests..")
    yield
    logger.info("Verifact is shutting down..")

app = FastAPI(
    title="Verifact API",
    description="AI-powered news authenticity checker",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
ALLOWED_ORIGINS = [
    o.strip() for o in allowed_origins_env.split(",") if o.strip() and o.strip() != "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

app.include_router(router)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "static"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def catch_all(full_path: str):
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        raise HTTPException(status_code=404, detail="Frontend not found")
