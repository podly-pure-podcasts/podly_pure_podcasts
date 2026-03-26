import base64
import hashlib
import os
from typing import Optional

from flask import current_app


def _get_secret_material() -> str:
    secret_any = current_app.config.get("SECRET_KEY") or os.environ.get("PODLY_SECRET_KEY")
    if not isinstance(secret_any, str) or not secret_any.strip():
        raise RuntimeError("SECRET_KEY is required for secret encryption.")
    return secret_any


def _build_fernet():
    try:
        from cryptography.fernet import Fernet  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "cryptography package is required to encrypt saved LLM keys."
        ) from exc

    digest = hashlib.sha256(_get_secret_material().encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(raw_secret: str) -> str:
    if not raw_secret or not raw_secret.strip():
        raise ValueError("Secret cannot be empty.")
    return _build_fernet().encrypt(raw_secret.strip().encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> Optional[str]:
    if not ciphertext or not ciphertext.strip():
        return None

    try:
        token = ciphertext.strip().encode("utf-8")
        return _build_fernet().decrypt(token).decode("utf-8")
    except Exception:
        return None
