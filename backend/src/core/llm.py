"""Shared LLM access: cached provider clients, JSON completions and token streaming.

Messages use the OpenAI shape: [{"role": "user" | "assistant", "content": str}].
"""
import asyncio
import json
import logging
import time
import re
from functools import lru_cache
from typing import Any, AsyncIterator, Dict, List, Optional
from src.config import settings

logger = logging.getLogger(__name__)

Message = Dict[str, str]


class LLMUnavailableError(RuntimeError):
    """Raised when no configured LLM provider produced a response."""


@lru_cache(maxsize=1)
def openai_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=1)


@lru_cache(maxsize=1)
def gemini_client():
    from google import genai
    from google.genai import types
    # One quick retry only: on 429/503 it is faster to move to the next fallback model
    # than to sit in the SDK's long exponential backoff.
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=settings.LLM_TIMEOUT_SECONDS * 1000,
            retry_options=types.HttpRetryOptions(attempts=2, initial_delay=0.5, max_delay=2.0),
        ),
    )


def active_provider() -> Optional[str]:
    """Pick the provider named by API_USED, falling back to whichever key exists."""
    if settings.API_USED == "openai" and settings.OPENAI_API_KEY:
        return "openai"
    if settings.API_USED == "gemini" and settings.GEMINI_API_KEY:
        return "gemini"
    if settings.GEMINI_API_KEY:
        return "gemini"
    if settings.OPENAI_API_KEY:
        return "openai"
    return None


def _gemini_contents(messages: List[Message]) -> List[Dict[str, Any]]:
    return [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in messages
    ]


MODEL_COOLDOWN_SECONDS = 60
_model_cooldown: Dict[str, float] = {}


def _mark_failed(model: str, error: Exception) -> None:
    """Skip a model for a while after an overload/timeout error, so every request
    does not pay for the same failure before reaching a working fallback."""
    text = f"{type(error).__name__} {error}".lower()
    if any(k in text for k in ("503", "429", "unavailable", "resource_exhausted", "timeout", "overloaded")):
        _model_cooldown[model] = time.monotonic() + MODEL_COOLDOWN_SECONDS


def _gemini_models(model: Optional[str] = None) -> List[str]:
    models = list(dict.fromkeys(([model] if model else []) + settings.gemini_models))
    now = time.monotonic()
    healthy = [m for m in models if _model_cooldown.get(m, 0) <= now]
    # If everything is cooling down, still try them all rather than fail outright.
    return healthy or models


async def complete(
    messages: List[Message],
    system: Optional[str] = None,
    temperature: float = 0.2,
    json_mode: bool = False,
    model: Optional[str] = None,
) -> str:
    """Return a full (non-streamed) completion."""
    provider = active_provider()
    if provider == "openai":
        kwargs: Dict[str, Any] = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        resp = await openai_client().chat.completions.create(
            model=model or settings.OPENAI_MODEL,
            messages=msgs,
            temperature=temperature,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    if provider == "gemini":
        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
        )
        last_error: Optional[Exception] = None
        for m in _gemini_models(model):
            try:
                resp = await asyncio.wait_for(
                    gemini_client().aio.models.generate_content(
                        model=m, contents=_gemini_contents(messages), config=config
                    ),
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
                if resp and resp.text:
                    return resp.text
            except Exception as e:
                last_error = e
                _mark_failed(m, e)
                logger.warning(f"Gemini model {m} failed ({type(e).__name__}: {e}); trying next candidate.")
        raise LLMUnavailableError(f"All Gemini models failed: {last_error}")

    raise LLMUnavailableError("No OPENAI_API_KEY or GEMINI_API_KEY configured.")


async def stream(
    messages: List[Message],
    system: Optional[str] = None,
    temperature: float = 0.3,
) -> AsyncIterator[str]:
    """Yield answer text as the provider produces it."""
    provider = active_provider()
    if provider == "openai":
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        resp = await openai_client().chat.completions.create(
            model=settings.OPENAI_MODEL, messages=msgs, temperature=temperature, stream=True
        )
        async for chunk in resp:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        return

    if provider == "gemini":
        from google.genai import types
        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
        last_error: Optional[Exception] = None
        for m in _gemini_models():
            produced = False
            try:
                response = await asyncio.wait_for(
                    gemini_client().aio.models.generate_content_stream(
                        model=m, contents=_gemini_contents(messages), config=config
                    ),
                    timeout=settings.LLM_TIMEOUT_SECONDS,
                )
                iterator = response.__aiter__()
                while True:
                    try:
                        # Bound the wait for every chunk so a stalled stream cannot hang the chat
                        chunk = await asyncio.wait_for(iterator.__anext__(), timeout=settings.LLM_TIMEOUT_SECONDS)
                    except StopAsyncIteration:
                        break
                    if chunk.text:
                        produced = True
                        yield chunk.text
                if produced:
                    return
            except Exception as e:
                last_error = e
                _mark_failed(m, e)
                if produced:
                    # Text already reached the user; switching models now would duplicate it.
                    raise
                logger.warning(f"Gemini streaming with {m} failed ({type(e).__name__}: {e}); trying next candidate.")
        raise LLMUnavailableError(f"All Gemini models failed: {last_error}")

    raise LLMUnavailableError("No OPENAI_API_KEY or GEMINI_API_KEY configured.")


def parse_json_object(raw: str) -> Dict[str, Any]:
    """Parse a JSON object from model output, tolerating ``` fences or surrounding prose."""
    raw = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if fenced:
        raw = fenced.group(1)
    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object in model output")
    # raw_decode reads exactly one object and ignores whatever follows it, so prose
    # after the JSON or a second concatenated object (seen with flash-lite) is tolerated.
    value, _ = json.JSONDecoder().raw_decode(raw[start:])
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value
