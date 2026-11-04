from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.writer.client import writer_client
from shared import defaults as DEFAULTS

# Providers that accept the OpenAI-style `service_tier` kwarg via litellm.
# Anthropic, Groq, xAI, etc. do not, so we skip the kwarg for those.
_SERVICE_TIER_MODEL_PREFIXES = ("gemini/", "openai/")
_OPENAI_MODEL_PREFIXES = ("gpt-", "o1", "o3", "o4")
_VALID_SERVICE_TIERS = {"default", "flex", "priority", "auto"}


def model_supports_service_tier(model_name: str | None) -> bool:
    if not model_name:
        return False
    if model_name.startswith(_SERVICE_TIER_MODEL_PREFIXES):
        return True
    return "/" not in model_name and model_name.startswith(_OPENAI_MODEL_PREFIXES)


def _model_supports_flex_tier(model_name: str | None) -> bool:
    if not model_name:
        return False
    if model_name.startswith("gemini/"):
        return True
    if not (
        model_name.startswith("openai/")
        or ("/" not in model_name and model_name.startswith(_OPENAI_MODEL_PREFIXES))
    ):
        return False

    # OpenAI Flex has limited model availability. LiteLLM's price table tracks
    # that support with explicit Flex rates, which avoids sending a tier that
    # OpenAI will reject while staying current as LiteLLM adds models.
    import litellm

    normalized_name = model_name.removeprefix("openai/")
    cost_entry = litellm.model_cost.get(normalized_name, {})
    return all(
        key in cost_entry
        for key in ("input_cost_per_token_flex", "output_cost_per_token_flex")
    )


def _resolved_tier(config: Any) -> str:
    tier = getattr(config, "llm_service_tier", DEFAULTS.LLM_SERVICE_TIER)
    tier = (tier or DEFAULTS.LLM_SERVICE_TIER).strip().lower()
    if tier not in _VALID_SERVICE_TIERS:
        return DEFAULTS.LLM_SERVICE_TIER
    return tier


def record_service_tier_on_model_call(
    model_call_id: int | None,
    completion_args: dict[str, Any],
    *,
    logger: logging.Logger,
    log_prefix: str = "ModelCall",
) -> None:
    """Persist `service_tier` from completion_args onto the ModelCall row.

    Best-effort: silently skips when there's no model_call_id (best-effort
    upsert never returned one) or the writer call fails -- the LLM call itself
    is the load-bearing operation, this is just so the debug UI can show
    which tier was used. Writes NULL when the call ran at the default tier
    (`service_tier` absent from args).
    """
    if model_call_id is None:
        return
    tier = completion_args.get("service_tier")
    try:
        writer_client.update(
            "ModelCall",
            int(model_call_id),
            {"service_tier": tier},
            wait=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "%s: failed to record service_tier=%r on ModelCall %s: %s",
            log_prefix,
            tier,
            model_call_id,
            exc,
        )


def apply_service_tier(
    completion_args: dict[str, Any],
    config: Any,
) -> dict[str, Any]:
    """If a non-default service tier is configured AND the model supports
    `service_tier`, set it on the completion args in place.

    litellm forwards `service_tier` to OpenAI as-is and translates it for
    Gemini into `generationConfig.modelSelectionConfig.featureSelectionPreference`
    ('flex' -> PRIORITIZE_COST, 'priority' -> PRIORITIZE_QUALITY). No-op for
    other providers or when the tier is 'default'.
    """
    tier = _resolved_tier(config)
    if tier == "default":
        return completion_args
    if not model_supports_service_tier(completion_args.get("model")):
        return completion_args
    if tier == "flex" and not _model_supports_flex_tier(completion_args.get("model")):
        return completion_args
    completion_args["service_tier"] = tier
    return completion_args


def _record_effective_service_tier(
    response: Any,
    completion_args: dict[str, Any],
    *,
    model_call_id: int | None,
    logger: logging.Logger,
) -> Any:
    """Keep request state and ModelCall pricing aligned with the served tier."""
    response_tier = getattr(response, "service_tier", None)
    if response_tier is None and isinstance(response, dict):
        response_tier = response.get("service_tier")
    normalized_tier = str(response_tier or "").strip().lower()
    if normalized_tier in {"flex", "priority"}:
        completion_args["service_tier"] = normalized_tier
    elif normalized_tier in {"default", "auto"}:
        completion_args.pop("service_tier", None)
    record_service_tier_on_model_call(
        model_call_id,
        completion_args,
        logger=logger,
    )
    return response


def _is_tier_retryable(exc: Exception) -> bool:
    """Flex tiers (Gemini and OpenAI) return 503 (busy) or 429 under load."""
    err = str(exc).lower()
    if "503" in err or "service unavailable" in err:
        return True
    if "429" in err or "rate limit" in err or "resource_exhausted" in err:
        return True
    # LiteLLM sets `code` to a string ("429") and `status_code` to an int.
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, (int, str)) and str(value) in ("429", "503"):
            return True
    return False


def call_litellm_with_tier_retry(
    completion_args: dict[str, Any],
    *,
    config: Any,
    logger: logging.Logger,
    max_retries: int | None = None,
    base_delay: float | None = None,
    sleep: Any = time.sleep,
    model_call_id: int | None = None,
    before_attempt: Callable[[], None] | None = None,
) -> Any:
    """Run `litellm.completion(**args)` with Flex-aware retry + fallback.

    When `service_tier == "flex"`, on 503/429 errors back off exponentially up
    to `max_retries` times. On the final attempt, drop the `service_tier`
    kwarg so the call retries at the standard tier instead of failing. For
    'priority' / 'auto' / 'default' (or when the kwarg isn't set), this is a
    single straight-through `litellm.completion` invocation.

    ``before_attempt`` runs before every provider request, including Flex
    retries and the standard-tier fallback, so a rate limiter can pace each one.
    """
    import litellm  # local import to keep top-level imports cheap

    def completion(**kwargs: Any) -> Any:
        if before_attempt is not None:
            before_attempt()
        return litellm.completion(**kwargs)

    flex_active = completion_args.get("service_tier") == "flex"
    if not flex_active:
        response = completion(**completion_args)
        return _record_effective_service_tier(
            response,
            completion_args,
            model_call_id=model_call_id,
            logger=logger,
        )

    retries = (
        max_retries
        if max_retries is not None
        else DEFAULTS.LLM_SERVICE_TIER_MAX_RETRIES
    )
    delay = (
        base_delay
        if base_delay is not None
        else DEFAULTS.LLM_SERVICE_TIER_BASE_DELAY_SEC
    )

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            response = completion(**completion_args)
            return _record_effective_service_tier(
                response,
                completion_args,
                model_call_id=model_call_id,
                logger=logger,
            )
        except Exception as exc:
            last_err = exc
            if not _is_tier_retryable(exc):
                raise
            is_last = attempt == retries - 1
            if is_last:
                logger.warning(
                    "Flex tier exhausted after %d attempts (%s); "
                    "falling back to standard tier",
                    retries,
                    exc,
                )
                completion_args.pop("service_tier", None)
                response = completion(**completion_args)
                return _record_effective_service_tier(
                    response,
                    completion_args,
                    model_call_id=model_call_id,
                    logger=logger,
                )
            wait = delay * (2**attempt)
            logger.info(
                "Flex tier busy (%s); retrying in %.1fs (attempt %d/%d)",
                exc,
                wait,
                attempt + 1,
                retries,
            )
            sleep(wait)

    assert last_err is not None
    raise last_err


def render_prompt_and_upsert_model_call(
    *,
    template: Any,
    ad_start: float,
    ad_end: float,
    confidence: float,
    context_segments: Any,
    post_id: int | None,
    first_seq_num: int | None,
    last_seq_num: int | None,
    model_name: str,
    logger: logging.Logger,
    log_prefix: str,
) -> tuple[str, int | None]:
    prompt = template.render(
        ad_start=ad_start,
        ad_end=ad_end,
        ad_confidence=confidence,
        context_segments=context_segments,
    )

    model_call_id = try_upsert_model_call(
        post_id=post_id,
        first_seq_num=first_seq_num,
        last_seq_num=last_seq_num,
        model_name=model_name,
        prompt=prompt,
        logger=logger,
        log_prefix=log_prefix,
    )

    return prompt, model_call_id


def try_upsert_model_call(
    *,
    post_id: int | None,
    first_seq_num: int | None,
    last_seq_num: int | None,
    model_name: str,
    prompt: str,
    logger: logging.Logger,
    log_prefix: str,
) -> int | None:
    """Best-effort ModelCall creation.

    Returns model_call_id if successfully created/upserted, else None.
    """
    if post_id is None or first_seq_num is None or last_seq_num is None:
        return None

    try:
        res = writer_client.action(
            "upsert_model_call",
            {
                "post_id": post_id,
                "model_name": model_name,
                "first_segment_sequence_num": first_seq_num,
                "last_segment_sequence_num": last_seq_num,
                "prompt": prompt,
            },
            wait=True,
        )
        if res and res.success:
            return (res.data or {}).get("model_call_id")
    except Exception as exc:  # best-effort  # noqa: BLE001
        logger.warning("%s: failed to upsert ModelCall: %s", log_prefix, exc)

    return None


def try_update_model_call(
    model_call_id: int | None,
    *,
    status: str,
    response: str | None,
    error_message: str | None,
    logger: logging.Logger,
    log_prefix: str,
    usage: dict[str, int | None] | None = None,
    model_name: str | None = None,
    service_tier: str | None = None,
    prompt: str | None = None,
) -> None:
    """Best-effort ModelCall updater; no-op if call creation failed.

    When ``status == "success"`` and token usage is supplied, this also
    pre-computes ``estimated_cost_usd`` and passes it in the writer
    payload. litellm is already loaded in this process (it just ran the
    completion) so the price lookup is free here; the web process can
    then read the persisted column without paying the ~160 MiB
    ``import litellm`` cost.
    """
    if model_call_id is None:
        return

    data: dict[str, Any] = {
        "status": status,
        "response": response,
        "error_message": error_message,
        "retry_attempts": 1,
    }
    if usage:
        for field in (
            "prompt_tokens",
            "cached_prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            if usage.get(field) is not None:
                data[field] = usage[field]

    if status.startswith("success") and model_name and usage:
        cost = compute_estimated_cost_usd(
            model_name=model_name,
            service_tier=service_tier,
            prompt=prompt,
            usage=usage,
            logger=logger,
            log_prefix=log_prefix,
        )
        if cost is not None:
            data["estimated_cost_usd"] = cost

    try:
        writer_client.update(
            "ModelCall",
            int(model_call_id),
            data,
            wait=True,
        )
    except Exception as exc:  # best-effort  # noqa: BLE001
        logger.warning(
            "%s: failed to update ModelCall %s: %s",
            log_prefix,
            model_call_id,
            exc,
        )


def compute_estimated_cost_usd(
    *,
    model_name: str,
    service_tier: str | None,
    prompt: str | None,
    usage: dict[str, int | None],
    logger: logging.Logger,
    log_prefix: str,
) -> float | None:
    """Compute USD cost for a finalized LLM call.

    Runs in the short-lived processing worker, which has already paid the
    litellm import to make the completion call. Returns ``None`` when the
    call is non-billable (whisper) so the writer leaves the column
    NULL and the dashboard treats it as 0. Returns ``0.0`` (not None) when
    LiteLLM has no price entry — that's a known billable call we just
    can't price, distinct from an unpriced whisper row.
    """
    from app.llm_pricing import compute_model_call_cost, is_whisper_call

    if is_whisper_call(model_name, prompt):
        return None

    try:
        # `compute_model_call_cost` is typed against the ORM ModelCall but
        # only reads the same five fields we hand it here. Build a duck
        # object instead of importing the model — keeps this module free
        # of ORM imports.
        from types import SimpleNamespace

        proxy = SimpleNamespace(
            model_name=model_name,
            service_tier=service_tier,
            prompt=prompt,
            prompt_tokens=usage.get("prompt_tokens") or 0,
            cached_prompt_tokens=usage.get("cached_prompt_tokens") or 0,
            completion_tokens=usage.get("completion_tokens") or 0,
        )
        return round(compute_model_call_cost(proxy), 8)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s: failed to compute estimated_cost_usd: %s", log_prefix, exc)
        return None


def extract_litellm_content(response: Any) -> str:
    """Extracts the primary text content from a litellm completion response."""
    choices = getattr(response, "choices", None) or []
    choice = choices[0] if choices else None
    if not choice:
        return ""

    # Prefer chat content; fall back to text for completion-style responses
    content = getattr(getattr(choice, "message", None), "content", None) or ""
    if not content:
        content = getattr(choice, "text", "") or ""
    return str(content)


def extract_litellm_finish_reason(response: Any) -> str | None:
    """Extracts finish_reason from the first response choice, if present."""
    choices = getattr(response, "choices", None) or []
    choice = choices[0] if choices else None
    if not choice:
        return None

    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason is None and isinstance(choice, dict):
        finish_reason = choice.get("finish_reason")
    if finish_reason is None:
        return None
    return str(finish_reason)


def extract_litellm_usage(response: Any) -> dict[str, int | None]:
    """Extracts token usage fields from a litellm response object."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    def _maybe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:  # noqa: BLE001
            return None

    def _usage_field(name: str) -> int | None:
        if usage is None:
            return None
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        return _maybe_int(value)

    def _prompt_tokens_detail_field(name: str) -> int | None:
        if usage is None:
            return None
        details = getattr(usage, "prompt_tokens_details", None)
        if details is None and isinstance(usage, dict):
            details = usage.get("prompt_tokens_details")
        if details is None:
            return None
        value = getattr(details, name, None)
        if value is None and isinstance(details, dict):
            value = details.get(name)
        return _maybe_int(value)

    cached_prompt_tokens = _prompt_tokens_detail_field("cached_tokens")
    if cached_prompt_tokens is None:
        cached_prompt_tokens = _usage_field("cache_read_input_tokens")

    return {
        "prompt_tokens": _usage_field("prompt_tokens"),
        "cached_prompt_tokens": cached_prompt_tokens,
        "completion_tokens": _usage_field("completion_tokens"),
        "total_tokens": _usage_field("total_tokens"),
    }
