"""Input/output validation and security guardrails."""
import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Known prompt injection & exfiltration triggers
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?system\s+prompts", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|instructions|api\s+key|secret)", re.IGNORECASE),
    re.compile(r"what\s+is\s+the\s+(system\s+prompt|master\s+key|jwt\s+secret)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+dan\s+mode", re.IGNORECASE),
]

# Sensitive credentials that should never leak in generated text
CREDENTIAL_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE), # OpenAI keys
    re.compile(r"AIza[0-9A-Za-z-_]{35}", re.IGNORECASE), # Google API keys
    re.compile(r"Bearer\s+[a-zA-Z0-9-_\.]+", re.IGNORECASE),
    re.compile(r"postgres://[^\s]+:[^\s]+@", re.IGNORECASE),
]

def validate_input_query(query: str) -> Tuple[bool, str]:
    """
    Sanitize and inspect user query against injection attacks.
    Returns (is_safe, error_or_cleaned_message).
    """
    if not query or not query.strip():
        return False, "Query cannot be empty."

    cleaned_query = query.strip()

    for pattern in INJECTION_PATTERNS:
        if pattern.search(cleaned_query):
            logger.warning(f"Blocked potential prompt injection query: {cleaned_query[:60]}...")
            return False, "Your request was flagged by the security guardrail. Please ask a domain-related question."

    return True, cleaned_query

# Lightweight sliding window rate limiter
import time
from collections import defaultdict

_RATE_LIMIT_STORE = defaultdict(list)

def check_rate_limit(client_id: str, max_requests: int = 35, window_seconds: int = 60) -> bool:
    """Sliding window rate limit check (max 35 requests/minute)."""
    now = time.time()
    valid_window = [t for t in _RATE_LIMIT_STORE[client_id] if now - t < window_seconds]
    if len(valid_window) >= max_requests:
        return False
    valid_window.append(now)
    _RATE_LIMIT_STORE[client_id] = valid_window
    return True

def sanitize_output_text(text: str) -> str:
    """Redact any sensitive credentials or secrets in generated text before returning."""
    if not text:
        return text

    sanitized = text
    for pattern in CREDENTIAL_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)

    return sanitized
