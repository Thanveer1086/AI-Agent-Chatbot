"""Embedding provider helper supporting OpenAI and Google Gemini.

All vectors are cut to EXPECTED_EMBEDDING_DIM and L2-normalised so they match
the `vector(1536)` column and cosine queries.
"""
import hashlib
import logging
from typing import List, Sequence
from src.config import settings
from src.core.llm import gemini_client, openai_client

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


class EmbeddingUnavailableError(RuntimeError):
    """Raised when no embedding provider could produce vectors."""


def _normalize(values: Sequence[float]) -> List[float]:
    vals = list(values)[: settings.EXPECTED_EMBEDDING_DIM]
    if len(vals) < settings.EXPECTED_EMBEDDING_DIM:
        raise EmbeddingUnavailableError(
            f"Embedding model returned {len(vals)} dimensions; "
            f"{settings.EXPECTED_EMBEDDING_DIM} are required."
        )
    norm = sum(x * x for x in vals) ** 0.5 or 1.0
    return [x / norm for x in vals]


def vector_literal(vec: Sequence[float]) -> str:
    """Format a vector for a `$n::vector` query parameter."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def _mock_embedding(text: str) -> List[float]:
    raw = [float(b) / 255.0 for b in hashlib.sha256(text.encode("utf-8")).digest()]
    tiled = (raw * (settings.EXPECTED_EMBEDDING_DIM // len(raw) + 1))[: settings.EXPECTED_EMBEDDING_DIM]
    return _normalize(tiled)


async def _embed_batch(texts: List[str]) -> List[List[float]]:
    errors = []

    if settings.EMBEDDING_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        try:
            resp = await openai_client().embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=[t.replace("\n", " ") for t in texts],
            )
            return [_normalize(d.embedding) for d in sorted(resp.data, key=lambda d: d.index)]
        except Exception as e:
            errors.append(f"OpenAI: {e}")
            logger.error(f"OpenAI embedding generation failed: {e}")

    if settings.GEMINI_API_KEY and (settings.EMBEDDING_PROVIDER == "gemini" or not settings.OPENAI_API_KEY):
        try:
            model = settings.EMBEDDING_MODEL if "gemini" in settings.EMBEDDING_MODEL else "gemini-embedding-2"
            response = await gemini_client().aio.models.embed_content(model=model, contents=texts)
            if len(response.embeddings) != len(texts):
                raise EmbeddingUnavailableError(
                    f"Gemini returned {len(response.embeddings)} embeddings for {len(texts)} inputs"
                )
            return [_normalize(e.values) for e in response.embeddings]
        except Exception as e:
            errors.append(f"Gemini: {e}")
            logger.error(f"Gemini embedding generation failed with {settings.EMBEDDING_MODEL}: {e}")

    if settings.ALLOW_MOCK_EMBEDDINGS:
        logger.warning("ALLOW_MOCK_EMBEDDINGS is on: storing fake hash-based vectors (dev only).")
        return [_mock_embedding(t) for t in texts]

    detail = "; ".join(errors) if errors else "no OPENAI_API_KEY or GEMINI_API_KEY is configured"
    raise EmbeddingUnavailableError(f"Could not generate embeddings ({detail}).")


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Embed many texts, batching provider calls."""
    vectors: List[List[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = [t if t.strip() else " " for t in texts[start:start + BATCH_SIZE]]
        vectors.extend(await _embed_batch(batch))
    return vectors


async def get_embedding(text: str) -> List[float]:
    """Generate a dense vector for a single text chunk or query."""
    if not text or not text.strip():
        raise EmbeddingUnavailableError("Cannot embed empty text.")
    return (await _embed_batch([text]))[0]
