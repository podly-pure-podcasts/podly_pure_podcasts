import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.extensions import db
from app.models import LLMKeyProfile
from app.secret_store import decrypt_secret


LLM_ENV_KEY_VARS: tuple[str, ...] = (
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
)


LLM_PROVIDER_CATALOG: Dict[str, Dict[str, Any]] = {
    "groq": {
        "label": "Groq",
        "default_model": "groq/openai/gpt-oss-120b",
        "default_openai_base_url": None,
        "models": [
            "groq/openai/gpt-oss-120b",
            "groq/llama-3.3-70b-versatile",
            "groq/llama-3.1-8b-instant",
            "groq/deepseek-r1-distill-llama-70b",
            "groq/qwen-qwq-32b",
            "groq/gemma2-9b-it",
            "groq/mistral-saba-24b",
            "groq/llama-4-scout-17b-16e-instruct",
        ],
    },
    "xai": {
        "label": "xAI (Grok)",
        "default_model": "xai/grok-3",
        "default_openai_base_url": "https://api.x.ai/v1",
        "models": [
            "xai/grok-3",
            "xai/grok-3-mini",
        ],
    },
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4o-mini",
        "default_openai_base_url": None,
        "models": [
            "gpt-4o",
            "gpt-4.1",
            "gpt-4o-mini",
            "o3-mini",
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "default_model": "anthropic/claude-3-7-sonnet-latest",
        "default_openai_base_url": None,
        "models": [
            "anthropic/claude-3-7-sonnet-latest",
            "anthropic/claude-3-5-sonnet-latest",
            "anthropic/claude-3-5-haiku-latest",
        ],
    },
    "google": {
        "label": "Google Gemini",
        "default_model": "gemini/gemini-2.0-flash",
        "default_openai_base_url": None,
        "models": [
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-pro",
            "gemini/gemini-1.5-flash",
        ],
    },
    "custom": {
        "label": "Custom / Other",
        "default_model": None,
        "default_openai_base_url": None,
        "models": [],
    },
}


def mask_secret_preview(value: Any | None) -> Optional[str]:
    if value is None:
        return None
    try:
        secret = str(value).strip()
    except Exception:
        return None
    if not secret:
        return None
    if len(secret) <= 8:
        return secret
    return f"{secret[:4]}...{secret[-4:]}"


def normalize_provider(provider: Any | None) -> str:
    if not isinstance(provider, str):
        return "custom"
    norm = provider.strip().lower()
    return norm if norm in LLM_PROVIDER_CATALOG else "custom"


def infer_provider_from_model(model_name: Any | None) -> str:
    if not isinstance(model_name, str) or not model_name.strip():
        return "custom"

    model = model_name.strip().lower()
    if model.startswith("groq/"):
        return "groq"
    if model.startswith("xai/"):
        return "xai"
    if model.startswith("anthropic/"):
        return "anthropic"
    if model.startswith("gemini/"):
        return "google"
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    return "custom"


def infer_provider_from_key(key: str, fallback: str = "custom") -> str:
    secret = key.strip().lower()
    if secret.startswith("gsk_"):
        return "groq"
    if secret.startswith("xai-"):
        return "xai"
    if secret.startswith("sk-ant-"):
        return "anthropic"
    if secret.startswith("ai") and len(secret) > 20:
        return "google"
    if secret.startswith("sk-"):
        return "openai"
    return fallback


def infer_provider_from_env(env_var: str, key: str) -> str:
    if env_var == "GROQ_API_KEY":
        return "groq"
    if env_var == "XAI_API_KEY":
        return "xai"
    if env_var == "ANTHROPIC_API_KEY":
        return "anthropic"
    if env_var in {"GOOGLE_API_KEY", "GEMINI_API_KEY"}:
        return "google"
    if env_var == "OPENAI_API_KEY":
        return "openai"
    return infer_provider_from_key(key, "custom")


def is_llm_key_reference(value: Any | None) -> bool:
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    return candidate.startswith("env:") or candidate.startswith("profile:")


def parse_llm_profile_ref(value: Any | None) -> Optional[int]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate.startswith("profile:"):
        return None
    _, _, raw_id = candidate.partition(":")
    if not raw_id.isdigit():
        return None
    return int(raw_id)


def parse_llm_env_ref(value: Any | None) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate.startswith("env:"):
        return None
    _, _, env_var = candidate.partition(":")
    env_norm = env_var.strip()
    if env_norm not in LLM_ENV_KEY_VARS:
        return None
    return env_norm


def resolve_llm_api_key_reference(value: Any | None) -> Optional[str]:
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    env_var = parse_llm_env_ref(candidate)
    if env_var:
        env_key = os.environ.get(env_var)
        return env_key.strip() if isinstance(env_key, str) and env_key.strip() else None

    profile_id = parse_llm_profile_ref(candidate)
    if profile_id is not None:
        profile = db.session.get(LLMKeyProfile, profile_id)
        if profile is None:
            return None
        decrypted = decrypt_secret(profile.encrypted_api_key)
        return decrypted.strip() if isinstance(decrypted, str) and decrypted.strip() else None

    return candidate


def list_env_key_options() -> List[Dict[str, Any]]:
    options: List[Dict[str, Any]] = []
    for env_var in LLM_ENV_KEY_VARS:
        env_val = os.environ.get(env_var)
        if not isinstance(env_val, str) or not env_val.strip():
            continue

        provider = infer_provider_from_env(env_var, env_val)
        provider_info = LLM_PROVIDER_CATALOG.get(provider, LLM_PROVIDER_CATALOG["custom"])
        options.append(
            {
                "ref": f"env:{env_var}",
                "env_var": env_var,
                "provider": provider,
                "provider_label": provider_info["label"],
                "api_key_preview": mask_secret_preview(env_val),
                "default_model": provider_info.get("default_model"),
                "default_openai_base_url": provider_info.get("default_openai_base_url"),
            }
        )

    return options


def serialize_saved_key_profile(profile: LLMKeyProfile) -> Dict[str, Any]:
    provider = normalize_provider(profile.provider)
    provider_info = LLM_PROVIDER_CATALOG.get(provider, LLM_PROVIDER_CATALOG["custom"])
    return {
        "id": profile.id,
        "ref": f"profile:{profile.id}",
        "name": profile.name,
        "provider": provider,
        "provider_label": provider_info["label"],
        "api_key_preview": profile.api_key_preview,
        "default_model": profile.default_model,
        "default_openai_base_url": profile.openai_base_url,
        "created_at": (
            profile.created_at.isoformat()
            if isinstance(profile.created_at, datetime)
            else None
        ),
        "last_used_at": (
            profile.last_used_at.isoformat()
            if isinstance(profile.last_used_at, datetime)
            else None
        ),
    }


def build_llm_options_payload() -> Dict[str, Any]:
    providers: List[Dict[str, Any]] = []
    models: List[Dict[str, Any]] = []

    for provider_id, provider_info in LLM_PROVIDER_CATALOG.items():
        providers.append(
            {
                "id": provider_id,
                "label": provider_info["label"],
                "default_model": provider_info.get("default_model"),
                "default_openai_base_url": provider_info.get("default_openai_base_url"),
            }
        )

        for model_name in provider_info.get("models", []):
            models.append(
                {
                    "provider": provider_id,
                    "value": model_name,
                }
            )

    saved_profiles = (
        LLMKeyProfile.query.order_by(LLMKeyProfile.updated_at.desc(), LLMKeyProfile.id.desc()).all()
    )

    return {
        "providers": providers,
        "models": models,
        "env_keys": list_env_key_options(),
        "saved_keys": [serialize_saved_key_profile(profile) for profile in saved_profiles],
    }
