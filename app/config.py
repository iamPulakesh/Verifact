import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT   = Path(__file__).resolve().parents[1]
DATA_DIR       = PROJECT_ROOT / "data"
RAW_DATA_DIR   = DATA_DIR / "raw"

GROQ_API_KEY              = os.getenv("GROQ_API_KEY", "").strip()
TAVILY_API_KEY            = os.getenv("TAVILY_API_KEY", "").strip()
LLM_PROVIDER              = os.getenv("LLM_PROVIDER", "groq").strip().lower()
SAMBANOVA_API_KEY         = os.getenv("SAMBANOVA_API_KEY", "").strip()
SAMBANOVA_MODEL           = os.getenv("SAMBANOVA_MODEL", "gpt-oss-120b").strip()
GOOGLE_API_KEY            = os.getenv("GOOGLE_API_KEY", "").strip()
GOOGLE_MODEL              = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash").strip()
HF_TOKEN                  = os.getenv("HF_TOKEN", "").strip()
GOOGLE_FACTCHECK_API_KEY  = os.getenv("GOOGLE_FACTCHECK_API_KEY", "").strip()
LLM_MODEL                 = os.getenv("LLM_MODEL", "groq/compound").strip()
LLM_TEMPERATURE           = 0.1
LLM_MAX_TOKENS            = 4096

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2").strip()
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu").strip()
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384").strip())

PINECONE_API_KEY    = os.getenv("PINECONE_API_KEY", "").strip()
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "").strip()
PINECONE_CLOUD      = os.getenv("PINECONE_CLOUD", "aws").strip()
PINECONE_REGION     = os.getenv("PINECONE_REGION", "us-east-1").strip()

USE_GPU       = os.getenv("USE_GPU", "false").lower() == "true"
MAX_FILE_SIZE = 5 * 1024 * 1024

REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CHUNK_SIZE    = 500
CHUNK_OVERLAP = 50
RETRIEVAL_TOP_K     = 5
RETRIEVAL_FETCH_K   = 20
RETRIEVAL_LAMBDA    = 0.7   # MMR: 0 = max diversity, 1 = max relevance

MAX_CLAIMS          = 6     # max claims to extract per article
MAX_ARTICLE_CHARS   = 3000  # truncation limit for article text sent to LLM
MAX_SEARCH_QUERIES  = 2     # web search queries per fact-check


class _Settings:

    def __getattr__(self, name: str):
        val = globals().get(name)
        if val is not None:
            return val
        raise AttributeError(f"No setting named '{name}'")


settings = _Settings()
