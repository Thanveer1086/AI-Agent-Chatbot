"""Embedding providers: OpenAI, Google Gemini, or a local Qwen3 model.

Select one with EMBEDDING_PROVIDER. Every vector is EXPECTED_EMBEDDING_DIM long and
L2-normalised so it matches the `vector(N)` columns and cosine queries.

There is deliberately NO fallback between providers: vectors from different models
live in different spaces and cannot be compared, so mixing them would silently break
search. After switching provider, re-embed everything with:
    python -m src.scripts.reindex_embeddings
"""
import asyncio
import hashlib
import logging
import threading
from typing import List, Sequence

from src.config import settings
from src.core.llm import gemini_client, openai_client

logger = logging.getLogger(__name__)

API_BATCH_SIZE = 50


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the configured embedding provider could not produce vectors."""


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


# --------------------------------------------------------------------------- Qwen (local)
_local_model = None
_local_lock = threading.Lock()


def load_local_model():
    """Load the local Hugging Face model once (downloaded on first use into hf_cache)."""
    global _local_model
    with _local_lock:
        if _local_model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading local embedding model {settings.QWEN_EMBEDDING_MODEL} (first load may download it)...")
            _local_model = SentenceTransformer(
                settings.QWEN_EMBEDDING_MODEL,
                device="cpu",
                truncate_dim=settings.EXPECTED_EMBEDDING_DIM,
                # bfloat16 is the checkpoint default but is slow on many CPUs; float32 is
                # reliable everywhere and gives the same rankings.
                model_kwargs={"dtype": torch.float32},
            )
            logger.info("Local embedding model loaded.")
        return _local_model


def _encode_local(texts: List[str], is_query: bool) -> List[List[float]]:
    model = load_local_model()
    kwargs = {}
    # Qwen3-Embedding uses an instruction prompt for queries and a plain one for documents
    prompt_name = "query" if is_query else "document"
    if prompt_name in (getattr(model, "prompts", None) or {}):
        kwargs["prompt_name"] = prompt_name
    vectors = model.encode(
        texts,
        batch_size=settings.QWEN_BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
        **kwargs,
    )
    return [_normalize(v.tolist()) for v in vectors]


# --------------------------------------------------------------------------- API providers
async def _embed_openai(texts: List[str]) -> List[List[float]]:
    if not settings.OPENAI_API_KEY:
        raise EmbeddingUnavailableError("EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is not set.")
    kwargs = {}
    if settings.OPENAI_EMBEDDING_MODEL.startswith("text-embedding-3"):
        kwargs["dimensions"] = settings.EXPECTED_EMBEDDING_DIM
    resp = await openai_client().embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=[t.replace("\n", " ") for t in texts],
        **kwargs,
    )
    return [_normalize(d.embedding) for d in sorted(resp.data, key=lambda d: d.index)]


async def _embed_gemini(texts: List[str]) -> List[List[float]]:
    if not settings.GEMINI_API_KEY:
        raise EmbeddingUnavailableError("EMBEDDING_PROVIDER=gemini but GEMINI_API_KEY is not set.")
    from google.genai import types

    # Each text must be its own Content: a plain list[str] is treated as ONE
    # multi-part input and returns a single embedding.
    response = await gemini_client().aio.models.embed_content(
        model=settings.GEMINI_EMBEDDING_MODEL,
        contents=[types.Content(parts=[types.Part(text=t)]) for t in texts],
        config=types.EmbedContentConfig(output_dimensionality=settings.EXPECTED_EMBEDDING_DIM),
    )
    if len(response.embeddings) != len(texts):
        raise EmbeddingUnavailableError(
            f"Gemini returned {len(response.embeddings)} embeddings for {len(texts)} inputs"
        )
    return [_normalize(e.values) for e in response.embeddings]


# --------------------------------------------------------------------------- public API
async def _embed_batch(texts: List[str], is_query: bool) -> List[List[float]]:
    provider = settings.EMBEDDING_PROVIDER
    try:
        if provider == "qwen":
            return await asyncio.to_thread(_encode_local, texts, is_query)
        if provider == "openai":
            return await _embed_openai(texts)
        if provider == "gemini":
            return await _embed_gemini(texts)
        raise EmbeddingUnavailableError(f"Unknown EMBEDDING_PROVIDER '{provider}'")
    except EmbeddingUnavailableError:
        if settings.ALLOW_MOCK_EMBEDDINGS:
            logger.warning("ALLOW_MOCK_EMBEDDINGS is on: using fake hash-based vectors (dev only).")
            return [_mock_embedding(t) for t in texts]
        raise
    except Exception as e:
        logger.error(f"{provider} embedding failed ({settings.embedding_model_name}): {e}")
        if settings.ALLOW_MOCK_EMBEDDINGS:
            logger.warning("ALLOW_MOCK_EMBEDDINGS is on: using fake hash-based vectors (dev only).")
            return [_mock_embedding(t) for t in texts]
        raise EmbeddingUnavailableError(f"Could not generate embeddings with {provider}: {e}") from e


async def get_embeddings(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Embed many texts (documents by default), batching provider calls."""
    if not texts:
        return []
    batch = settings.QWEN_BATCH_SIZE * 4 if settings.EMBEDDING_PROVIDER == "qwen" else API_BATCH_SIZE
    vectors: List[List[float]] = []
    for start in range(0, len(texts), batch):
        chunk = [t if t.strip() else " " for t in texts[start:start + batch]]
        vectors.extend(await _embed_batch(chunk, is_query))
    return vectors


async def get_embedding(text: str, is_query: bool = True) -> List[float]:
    """Embed a single text. Defaults to query mode (search questions)."""
    if not text or not text.strip():
        raise EmbeddingUnavailableError("Cannot embed empty text.")
    return (await _embed_batch([text], is_query))[0]
