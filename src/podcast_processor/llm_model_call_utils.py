from __future__ import annotations

import logging
from typing import Any

from app.writer.client import writer_client


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
) -> None:
    """Best-effort ModelCall updater; no-op if call creation failed."""
    if model_call_id is None:
        return

    try:
        writer_client.update(
            "ModelCall",
            int(model_call_id),
            {
                "status": status,
                "response": response,
                "error_message": error_message,
                "retry_attempts": 1,
            },
            wait=True,
        )
    except Exception as exc:  # best-effort  # noqa: BLE001
        logger.warning(
            "%s: failed to update ModelCall %s: %s",
            log_prefix,
            model_call_id,
            exc,
        )


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

    return {
        "prompt_tokens": _usage_field("prompt_tokens"),
        "completion_tokens": _usage_field("completion_tokens"),
        "total_tokens": _usage_field("total_tokens"),
    }
