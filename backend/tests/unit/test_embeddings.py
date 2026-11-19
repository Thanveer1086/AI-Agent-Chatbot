"""Embedding provider selection, dimension rules and the no-cross-provider-fallback rule."""
import pytest
from pydantic import ValidationError

from src.config import Settings, settings
from src.core.rag import embeddings


def test_qwen_dimension_cannot_exceed_1024():
    with pytest.raises(ValidationError):
        Settings(EMBEDDING_PROVIDER="qwen", EXPECTED_EMBEDDING_DIM=1536)


def test_each_provider_uses_its_own_model_setting():
    assert Settings(EMBEDDING_PROVIDER="qwen").embedding_model_name == Settings().QWEN_EMBEDDING_MODEL
    assert Settings(EMBEDDING_PROVIDER="gemini").embedding_model_name == Settings().GEMINI_EMBEDDING_MODEL
    assert Settings(EMBEDDING_PROVIDER="openai").embedding_model_name == Settings().OPENAI_EMBEDDING_MODEL


def test_vectors_are_cut_to_dimension_and_normalised(monkeypatch):
    monkeypatch.setattr(settings, "EXPECTED_EMBEDDING_DIM", 4)
    v = embeddings._normalize([3.0, 4.0, 0.0, 0.0, 99.0])
    assert len(v) == 4 and abs(sum(x * x for x in v) - 1.0) < 1e-9


async def test_qwen_provider_passes_query_flag(monkeypatch):
    calls = []

    def fake_encode(texts, is_query):
        calls.append(is_query)
        return [[1.0] + [0.0] * (settings.EXPECTED_EMBEDDING_DIM - 1) for _ in texts]

    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "qwen")
    monkeypatch.setattr(embeddings, "_encode_local", fake_encode)
    await embeddings.get_embedding("question?")
    await embeddings.get_embeddings(["doc one", "doc two"])
    assert calls == [True, False]  # queries vs documents use different prompts


async def test_no_silent_fallback_to_another_provider(monkeypatch):
    # OpenAI selected but no key: must fail, never quietly use Gemini vectors instead.
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings, "ALLOW_MOCK_EMBEDDINGS", False)

    async def must_not_call(texts):
        raise AssertionError("Gemini must not be used when the provider is openai")

    monkeypatch.setattr(embeddings, "_embed_gemini", must_not_call)
    with pytest.raises(embeddings.EmbeddingUnavailableError):
        await embeddings.get_embeddings(["text"])
