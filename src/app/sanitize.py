"""Utilities for redacting sensitive values (API keys, secrets) from strings."""

import re

# Patterns that look like API keys: long alphanumeric strings, often with dashes
_KEY_PATTERN = re.compile(
    r"""((?:api[_-]?key|secret|token|password|auth)[=:\s'"]+)"""
    r"""([A-Za-z0-9\-_]{8,})""",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    """Replace likely secret values in *text* with a placeholder."""
    return _KEY_PATTERN.sub(lambda m: m.group(1) + "***REDACTED***", text)
