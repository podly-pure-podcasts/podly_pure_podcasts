"""Estimate legacy ModelCall token usage from stored prompt/response text."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.models import ModelCall
from app.writer.client import writer_client

logger = logging.getLogger("global_logger")


@dataclass
class ModelBackfillStats:
    would_update: int = 0
    updated: int = 0
    tokenizer_errors: int = 0


@dataclass
class TokenBackfillResult:
    apply: bool
    scanned: int = 0
    eligible: int = 0
    would_update: int = 0
    updated: int = 0
    skipped_existing: int = 0
    skipped_non_llm: int = 0
    skipped_missing_text: int = 0
    skipped_tokenizer_error: int = 0
    failed_updates: int = 0
    models: dict[str, ModelBackfillStats] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "apply": self.apply,
            "scanned": self.scanned,
            "eligible": self.eligible,
            "would_update": self.would_update,
            "updated": self.updated,
            "skipped_existing": self.skipped_existing,
            "skipped_non_llm": self.skipped_non_llm,
            "skipped_missing_text": self.skipped_missing_text,
            "skipped_tokenizer_error": self.skipped_tokenizer_error,
            "failed_updates": self.failed_updates,
            "models": {
                model_name: {
                    "would_update": stats.would_update,
                    "updated": stats.updated,
                    "tokenizer_errors": stats.tokenizer_errors,
                }
                for model_name, stats in sorted(self.models.items())
            },
            "errors": self.errors,
        }


def _is_legacy_billable_llm_call(call: ModelCall) -> bool:
    if not (call.status or "").startswith("success"):
        return False
    name = (call.model_name or "").lower()
    if "whisper" in name or call.prompt == "Whisper transcription job":
        return False
    return True


def _estimate_text_tokens(model_name: str, text: str) -> int:
    import litellm

    return int(litellm.token_counter(model=model_name, text=text))


def _model_stats(result: TokenBackfillResult, model_name: str) -> ModelBackfillStats:
    stats = result.models.get(model_name)
    if stats is None:
        stats = ModelBackfillStats()
        result.models[model_name] = stats
    return stats


def _append_error(
    result: TokenBackfillResult,
    call: ModelCall,
    error: str,
) -> None:
    if len(result.errors) >= 20:
        return
    result.errors.append(
        {
            "model_call_id": call.id,
            "model_name": call.model_name,
            "error": error,
        }
    )


def _build_update_payload(call: ModelCall) -> dict[str, int | float | None]:
    prompt_tokens = call.prompt_tokens
    completion_tokens = call.completion_tokens

    if prompt_tokens is None:
        prompt_tokens = _estimate_text_tokens(call.model_name, call.prompt or "")
    if completion_tokens is None:
        completion_tokens = _estimate_text_tokens(call.model_name, call.response or "")

    payload: dict[str, int | float | None] = {}
    if call.prompt_tokens is None:
        payload["prompt_tokens"] = prompt_tokens
    if call.completion_tokens is None:
        payload["completion_tokens"] = completion_tokens
    if call.total_tokens is None:
        payload["total_tokens"] = int(prompt_tokens or 0) + int(completion_tokens or 0)

    # While we already paid the LiteLLM import to estimate tokens, also
    # price the call so the cost dashboard / stats modal don't need a
    # second backfill pass. Only fill if the column is currently NULL —
    # never overwrite an existing value.
    if call.estimated_cost_usd is None:
        from types import SimpleNamespace

        from app.llm_pricing import compute_model_call_cost

        proxy = SimpleNamespace(
            model_name=call.model_name,
            service_tier=call.service_tier,
            prompt_tokens=prompt_tokens,
            cached_prompt_tokens=call.cached_prompt_tokens,
            completion_tokens=completion_tokens,
        )
        try:
            payload["estimated_cost_usd"] = round(compute_model_call_cost(proxy), 8)
        except Exception:  # noqa: BLE001
            # Pricing is best-effort; the explicit estimated-cost backfill
            # endpoint can retry later.
            pass
    return payload


def backfill_model_call_token_usage(
    *,
    apply: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Estimate token counts for legacy LLM ModelCall rows.

    Cached prompt tokens are intentionally not backfilled. They depend on the
    provider/cache state at call time and cannot be inferred from stored text.
    """
    query = ModelCall.query.order_by(ModelCall.id.asc())
    if limit is not None:
        query = query.limit(limit)

    result = TokenBackfillResult(apply=apply)
    for call in query:
        result.scanned += 1
        model_name = call.model_name or ""
        if not _is_legacy_billable_llm_call(call):
            result.skipped_non_llm += 1
            continue
        result.eligible += 1
        if (
            call.prompt_tokens is not None
            and call.completion_tokens is not None
            and call.total_tokens is not None
        ):
            result.skipped_existing += 1
            continue
        if call.prompt is None or call.response is None:
            result.skipped_missing_text += 1
            continue

        stats = _model_stats(result, model_name)
        try:
            update_payload = _build_update_payload(call)
        except Exception as exc:  # noqa: BLE001
            result.skipped_tokenizer_error += 1
            stats.tokenizer_errors += 1
            _append_error(result, call, str(exc))
            continue

        if not update_payload:
            result.skipped_existing += 1
            continue

        result.would_update += 1
        stats.would_update += 1
        if not apply:
            continue

        write_result = writer_client.update(
            "ModelCall", call.id, update_payload, wait=True
        )
        if write_result and write_result.success:
            result.updated += 1
            stats.updated += 1
        else:
            result.failed_updates += 1
            error = (
                write_result.error
                if write_result and write_result.error
                else "writer update failed"
            )
            logger.warning(
                "Failed to backfill token usage for ModelCall %s: %s",
                call.id,
                error,
            )
            _append_error(result, call, error)

    return result.to_dict()
