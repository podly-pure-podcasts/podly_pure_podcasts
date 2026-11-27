"""User-Agent for Podly's outbound HTTP requests (feeds, audio, API calls)."""

from __future__ import annotations

import os

DEFAULT_USER_AGENT = "Podly/1.0"


def get_user_agent() -> str:
    """Return the User-Agent, overridable per deployment via PODLY_USER_AGENT."""
    override = (os.environ.get("PODLY_USER_AGENT") or "").strip()
    return override or DEFAULT_USER_AGENT


def user_agent_headers(**extra: str | None) -> dict[str, str]:
    """User-Agent header plus extras; extras passed as None are dropped."""
    headers: dict[str, str] = {"User-Agent": get_user_agent()}
    headers.update({k: v for k, v in extra.items() if v is not None})
    return headers
