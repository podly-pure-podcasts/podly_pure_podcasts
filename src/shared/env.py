"""Environment variable helpers."""

from __future__ import annotations

import os

GROQ_API_KEY_ENV = "GROQ_API_KEY"
GROQ_KEY_ENV = "GROQ_KEY"

# Gemini / Google Generative AI. Cloud Agents may set GOOGLE_API_KEY or
# GEMINI_KEY instead of the canonical GEMINI_API_KEY. Do not treat GROQ_KEY
# as a Gemini credential.
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
GEMINI_KEY_ENV = "GEMINI_KEY"
GOOGLE_API_KEY_ENV = "GOOGLE_API_KEY"
GOOGLE_GENERATIVE_AI_API_KEY_ENV = "GOOGLE_GENERATIVE_AI_API_KEY"


def env_first(*names: str) -> str:
    """Return the first non-empty stripped environment value among *names*."""
    for name in names:
        raw = os.environ.get(name)
        if raw is None:
            continue
        value = raw.strip()
        if value:
            return value
    return ""


def groq_api_key() -> str:
    """Canonical GROQ_API_KEY, else Cloud Agents GROQ_KEY alias."""
    return env_first(GROQ_API_KEY_ENV, GROQ_KEY_ENV)


def gemini_api_key() -> str:
    """Gemini/Google key for gold-judge and confirm paths.

    Canonical ``GEMINI_API_KEY``, then ``GEMINI_KEY``, ``GOOGLE_API_KEY``,
    and ``GOOGLE_GENERATIVE_AI_API_KEY``. Never falls back to ``GROQ_KEY``.
    """
    return env_first(
        GEMINI_API_KEY_ENV,
        GEMINI_KEY_ENV,
        GOOGLE_API_KEY_ENV,
        GOOGLE_GENERATIVE_AI_API_KEY_ENV,
    )
