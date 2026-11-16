"""Embedding provider helper supporting OpenAI and Google Gemini."""
import logging
from typing import List
from src.config import settings

logger = logging.getLogger(__name__)

async def get_embedding(text: str) -> List[float]:
    """Generate dense vector embedding for a single text chunk or query."""
    if not text or not text.strip():
        return [0.0] * settings.EXPECTED_EMBEDDING_DIM

    # 1. OpenAI Embeddings
    if settings.EMBEDDING_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            resp = await client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text.replace("\n", " "),
            )
            return resp.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")

    # 2. Gemini Embeddings
    if settings.GEMINI_API_KEY and (settings.EMBEDDING_PROVIDER == "gemini" or not settings.OPENAI_API_KEY):
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            model_to_use = settings.EMBEDDING_MODEL if "gemini" in settings.EMBEDDING_MODEL else "gemini-embedding-2"
            response = await client.aio.models.embed_content(
                model=model_to_use,
                contents=text,
            )
            raw_vals = response.embeddings[0].values[:settings.EXPECTED_EMBEDDING_DIM]
            norm = sum(x * x for x in raw_vals) ** 0.5 or 1.0
            return [x / norm for x in raw_vals]
        except Exception as e:
            logger.error(f"Gemini embedding generation failed with {settings.EMBEDDING_MODEL}: {e}")

    # Fallback mock embedding for offline development / test mode
    logger.warning("No active embedding API key detected. Using normalized pseudo-random embedding for dev.")
    import hashlib
    hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [float(b) / 255.0 for b in hash_bytes]
    # Expand to expected dimension (1536)
    tiled = (raw * (settings.EXPECTED_EMBEDDING_DIM // len(raw) + 1))[:settings.EXPECTED_EMBEDDING_DIM]
    norm = sum(x * x for x in tiled) ** 0.5 or 1.0
    return [x / norm for x in tiled]
