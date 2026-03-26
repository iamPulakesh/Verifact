import logging
import time

from pinecone import Pinecone, ServerlessSpec
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore

from app.config import settings

logger = logging.getLogger(__name__)

_embeddings  = None
_vectorstore = None

EMBEDDING_MODEL  = settings.EMBEDDING_MODEL
PINECONE_INDEX   = settings.PINECONE_INDEX_NAME


def get_embeddings():
    """
    Load the embedding model once and reuse it.
    paraphrase-multilingual-MiniLM-L12-v2: ~134MB, 384-dimensional vectors.
    Downloads automatically on first run from HuggingFace.
    """
    global _embeddings
    if _embeddings is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        logger.info("(First run downloads the model -- subsequent runs are instant)")
        model_kwargs = {"device": settings.EMBEDDING_DEVICE}
        if settings.HF_TOKEN:
            model_kwargs["token"] = settings.HF_TOKEN
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs=model_kwargs,
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("Embedding model loaded.")
    return _embeddings


def _get_pinecone_client():
    """Get a Pinecone client instance."""
    return Pinecone(api_key=settings.PINECONE_API_KEY)


def ensure_index_exists():
    """
    Create the Pinecone serverless index if it doesn't already exist.
    Free tier supports 1 index, 100K vectors, up to 384 dimensions.
    """
    pc = _get_pinecone_client()
    existing = [idx.name for idx in pc.list_indexes()]

    if PINECONE_INDEX not in existing:
        logger.info("Creating Pinecone index: %s", PINECONE_INDEX)
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=settings.EMBEDDING_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=settings.PINECONE_CLOUD,
                region=settings.PINECONE_REGION,
            ),
        )
        while not pc.describe_index(PINECONE_INDEX).status.get("ready"):
            logger.info("Waiting for Pinecone index to be ready...")
            time.sleep(2)
        logger.info("Pinecone index '%s' created and ready.", PINECONE_INDEX)
    else:
        logger.info("Pinecone index '%s' already exists.", PINECONE_INDEX)


def get_vectorstore():
    """
    Connect to the Pinecone vectorstore (creates index if needed).
    Returns a LangChain PineconeVectorStore instance.
    """
    global _vectorstore

    if _vectorstore is not None:
        return _vectorstore

    ensure_index_exists()

    logger.info("Connecting to Pinecone index: %s", PINECONE_INDEX)
    _vectorstore = PineconeVectorStore(
        index_name=PINECONE_INDEX,
        embedding=get_embeddings(),
        pinecone_api_key=settings.PINECONE_API_KEY,
    )

    count = get_index_vector_count()
    logger.info("Pinecone connected -- %d vectors in index.", count)
    return _vectorstore


def get_index_vector_count() -> int:
    """Get the total number of vectors in the Pinecone index."""
    try:
        pc = _get_pinecone_client()
        index = pc.Index(PINECONE_INDEX)
        stats = index.describe_index_stats()
        return stats.total_vector_count
    except Exception:
        return 0


def get_collection_stats() -> dict:
    """Return stats about the vectorstore for display in the UI."""
    try:
        count = get_index_vector_count()
        return {
            "total_documents": count,
            "index_name": PINECONE_INDEX,
            "embedding_model": EMBEDDING_MODEL,
            "ready": count > 0,
        }
    except Exception:
        return {
            "total_documents": 0,
            "index_name": PINECONE_INDEX,
            "embedding_model": EMBEDDING_MODEL,
            "ready": False,
        }