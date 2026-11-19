"""LiteLLM-backed per-token pricing helpers.

These are the only functions in the codebase that touch ``litellm.model_cost``.
Importing them does NOT import litellm — every call site imports lazily so
processes that never run cost math don't pay the ~160 MiB ``import litellm``
cost.

The processing worker calls ``compute_model_call_cost`` when it finalizes a
ModelCall and stores the result on ``ModelCall.estimated_cost_usd``. Web
routes read that column; only the admin backfill endpoints price in the web
process and import litellm there.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.models import ModelCall

logger = logging.getLogger("global_logger")


class ModelCallLike(Protocol):
    """Structural type for ``compute_model_call_cost``.

    The processing worker hands in a ``SimpleNamespace`` shaped like a
    ``ModelCall``; cost_routes hands in the ORM row itself. Both satisfy
    this Protocol so we don't have to drag the SQLAlchemy class into
    modules that only need the attributes.
    """

    model_name: str
    service_tier: str | None
    prompt_tokens: int | None
    cached_prompt_tokens: int | None
    completion_tokens: int | None


def rate_from_litellm(model_name: str, key: str, service_tier: str | None) -> float:
    """Read a per-token price from LiteLLM's model cost map.

    ``key`` is one of ``"input_cost_per_token"``,
    ``"cache_read_input_token_cost"``, or ``"output_cost_per_token"``.
    The Flex tier gets a 0.5x discount applied here so callers can treat the
    returned rate as the effective per-token rate.
    """
    try:
        import litellm
    except Exception as exc:  # noqa: BLE001
        logger.warning("LiteLLM unavailable for cost calculation: %s", exc)
        return 0.0

    cost_entry = litellm.model_cost.get(model_name)
    if not cost_entry and "/" in model_name:
        cost_entry = litellm.model_cost.get(model_name.split("/", 1)[1])
    if not cost_entry:
        return 0.0

    normalized_tier = (service_tier or "default").lower()
    if normalized_tier != "default":
        tier_key = f"{key}_{normalized_tier}"
        if tier_key in cost_entry:
            return float(cost_entry[tier_key] or 0.0)
    base_rate = float(cost_entry.get(key) or 0.0)
    if normalized_tier == "flex":
        return base_rate * 0.5
    return base_rate


def compute_model_call_cost(call: ModelCallLike) -> float:
    """Calculate USD cost for a ModelCall from LiteLLM rates and persisted tokens.

    Returns 0.0 when the call has no token usage recorded or when LiteLLM
    has no price entry for the model.
    """
    prompt_tokens = int(call.prompt_tokens or 0)
    cached_prompt_tokens = int(call.cached_prompt_tokens or 0)
    completion_tokens = int(call.completion_tokens or 0)
    if prompt_tokens <= 0 and cached_prompt_tokens <= 0 and completion_tokens <= 0:
        return 0.0

    input_rate = rate_from_litellm(
        call.model_name, "input_cost_per_token", call.service_tier
    )
    cached_input_rate = rate_from_litellm(
        call.model_name, "cache_read_input_token_cost", call.service_tier
    )
    if cached_input_rate == 0.0 and cached_prompt_tokens > 0:
        cached_input_rate = input_rate
    output_rate = rate_from_litellm(
        call.model_name, "output_cost_per_token", call.service_tier
    )
    # OpenAI includes cached tokens in prompt_tokens. Charge that subset at
    # the cache-read rate instead of charging it once at each input rate.
    uncached_prompt_tokens = max(prompt_tokens - cached_prompt_tokens, 0)

    return (
        uncached_prompt_tokens * input_rate
        + cached_prompt_tokens * cached_input_rate
        + completion_tokens * output_rate
    )


def is_whisper_call(model_name: str, prompt: str | None) -> bool:
    name = (model_name or "").lower()
    if "whisper" in name:
        return True
    if prompt == "Whisper transcription job":
        return True
    # Historical local Whisper calls were stored as local_<model>.
    return name.startswith("local_")


def is_billable_llm_call(call: ModelCall) -> bool:
    if not (call.status or "").startswith("success"):
        return False
    if is_whisper_call(call.model_name, call.prompt):
        return False
    return True
