<<<<<<< HEAD
"""LLM-based boundary refiner.

Note: We intentionally share some call-setup patterns with WordBoundaryRefiner.
"""
=======
from __future__ import annotations
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

import json
import logging
import re
from dataclasses import dataclass
<<<<<<< HEAD
from pathlib import Path
from typing import Any

import litellm
from jinja2 import Template

from app.writer.client import writer_client
from shared.config import Config

# Internal defaults for boundary expansion; not user-configurable.
=======
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import litellm
from jinja2 import Template
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import ModelCall
from shared.config import Config, TestWhisperConfig
from shared.llm_utils import model_uses_max_completion_tokens

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
MAX_START_EXTENSION_SECONDS = 30.0
MAX_END_EXTENSION_SECONDS = 15.0


<<<<<<< HEAD
@dataclass
=======
def _extract_completion_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""

    choice = choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if content:
        return str(content)

    text = getattr(choice, "text", None)
    return str(text or "")


def _build_completion_args(
    *, config: Config, prompt: str, max_tokens: int
) -> Dict[str, Any]:
    messages = [{"role": "user", "content": prompt}]
    completion_args: Dict[str, Any] = {
        "model": config.llm_model,
        "messages": messages,
        "timeout": config.openai_timeout,
        "temperature": 0.1,
    }

    if config.llm_api_key:
        completion_args["api_key"] = config.llm_api_key
    if config.openai_base_url:
        completion_args["api_base"] = config.openai_base_url

    if model_uses_max_completion_tokens(config.llm_model):
        completion_args["max_completion_tokens"] = max_tokens
    else:
        completion_args["max_tokens"] = max_tokens

    return completion_args


def _get_or_create_refinement_model_call(
    *,
    config: Config,
    db_session: Any,
    model_call_query: Any,
    model_name_suffix: str,
    post_id: Optional[int],
    first_seq_num: Optional[int],
    last_seq_num: Optional[int],
    prompt: str,
) -> Optional[ModelCall]:
    if post_id is None or first_seq_num is None or last_seq_num is None:
        return None

    model_name = f"{config.llm_model}{model_name_suffix}"
    model_call: Optional[ModelCall] = (
        model_call_query.filter_by(
            post_id=post_id,
            model_name=model_name,
            first_segment_sequence_num=first_seq_num,
            last_segment_sequence_num=last_seq_num,
        )
        .order_by(ModelCall.timestamp.desc())
        .first()
    )

    if model_call is None:
        model_call = ModelCall(
            post_id=post_id,
            first_segment_sequence_num=first_seq_num,
            last_segment_sequence_num=last_seq_num,
            model_name=model_name,
            prompt=prompt,
            status="pending",
            timestamp=datetime.utcnow(),
        )
        try:
            db_session.add(model_call)
            db_session.commit()
        except IntegrityError:
            db_session.rollback()
            model_call = (
                model_call_query.filter_by(
                    post_id=post_id,
                    model_name=model_name,
                    first_segment_sequence_num=first_seq_num,
                    last_segment_sequence_num=last_seq_num,
                )
                .order_by(ModelCall.timestamp.desc())
                .first()
            )
            if model_call is None:
                raise

    model_call.prompt = prompt
    model_call.response = None
    model_call.error_message = None
    model_call.retry_attempts = 0
    model_call.status = "pending"
    model_call.timestamp = datetime.utcnow()
    db_session.add(model_call)
    db_session.commit()
    return model_call


def _update_refinement_model_call(
    *,
    db_session: Any,
    model_call: Optional[ModelCall],
    status: str,
    response: Optional[str],
    error_message: Optional[str],
) -> None:
    if model_call is None:
        return

    model_call.status = status
    model_call.response = response
    model_call.error_message = error_message
    model_call.retry_attempts = max(int(model_call.retry_attempts or 0), 1)
    db_session.add(model_call)
    db_session.commit()


@dataclass(slots=True)
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
class BoundaryRefinement:
    refined_start: float
    refined_end: float
    start_adjustment_reason: str
    end_adjustment_reason: str
<<<<<<< HEAD


class BoundaryRefiner:
    def __init__(self, config: Config, logger: logging.Logger | None = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
=======
    confidence_adjustment: float = 0.0


class BoundaryRefiner:
    def __init__(
        self,
        config: Config,
        logger: Optional[logging.Logger] = None,
        model_call_query: Any = None,
        db_session: Any = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("global_logger")
        self.model_call_query = model_call_query or ModelCall.query
        self.db_session = db_session or db.session
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        self.template = self._load_template()

    def _load_template(self) -> Template:
        path = (
<<<<<<< HEAD
            Path(__file__).resolve().parent.parent  # project src root
            / "boundary_refinement_prompt.jinja"
        )
        if path.exists():
            return Template(path.read_text())
        # Minimal fallback
=======
            Path(__file__).resolve().parent.parent / "boundary_refinement_prompt.jinja"
        )
        if path.exists():
            return Template(path.read_text())
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        return Template(
            """Refine ad boundaries.
Ad: {{ad_start}}s-{{ad_end}}s
{% for seg in context_segments %}[{{seg.start_time}}] {{seg.text}}
{% endfor %}
<<<<<<< HEAD
Return JSON: {"refined_start": {{ad_start}}, "refined_end": {{ad_end}}, "start_reason": "", "end_reason": ""}"""
=======
Return JSON: {"refined_start": {{ad_start}}, "refined_end": {{ad_end}}, "start_adjustment_reason": "", "end_adjustment_reason": ""}"""
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        )

    def refine(
        self,
        ad_start: float,
        ad_end: float,
        confidence: float,
<<<<<<< HEAD
        all_segments: list[dict[str, Any]],
        *,
        post_id: int | None = None,
        first_seq_num: int | None = None,
        last_seq_num: int | None = None,
    ) -> BoundaryRefinement:
        """Refine ad boundaries using LLM analysis and record the call in ModelCall."""
        self.logger.debug(
            "Refining boundaries",
            extra={
                "ad_start": ad_start,
                "ad_end": ad_end,
                "confidence": confidence,
                "segments_count": len(all_segments),
            },
        )
        context = self._get_context(ad_start, ad_end, all_segments)
        self.logger.debug(
            "Context window selected",
            extra={
                "context_size": len(context),
                "first_seg": context[0] if context else None,
            },
        )
=======
        all_segments: List[Dict[str, Any]],
        *,
        post_id: Optional[int] = None,
        first_seq_num: Optional[int] = None,
        last_seq_num: Optional[int] = None,
    ) -> BoundaryRefinement:
        context = self._get_context(
            ad_start,
            ad_end,
            all_segments,
            first_seq_num=first_seq_num,
            last_seq_num=last_seq_num,
        )
        if not context:
            return BoundaryRefinement(
                refined_start=ad_start,
                refined_end=ad_end,
                start_adjustment_reason="no_context",
                end_adjustment_reason="no_context",
            )
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

        prompt = self.template.render(
            ad_start=ad_start,
            ad_end=ad_end,
            ad_confidence=confidence,
            context_segments=context,
<<<<<<< HEAD
        )

        model_call_id: int | None = None
        raw_response: str | None = None

        # Record the intent to call the LLM when we have enough context to do so
        if (
            post_id is not None
            and first_seq_num is not None
            and last_seq_num is not None
        ):
            try:
                res = writer_client.action(
                    "upsert_model_call",
                    {
                        "post_id": post_id,
                        "model_name": self.config.llm_model,
                        "first_segment_sequence_num": first_seq_num,
                        "last_segment_sequence_num": last_seq_num,
                        "prompt": prompt,
                    },
                    wait=True,
                )
                if res and res.success:
                    model_call_id = (res.data or {}).get("model_call_id")
            except (
                Exception  # noqa: BLE001
            ) as e:  # best-effort; do not block refinement
                self.logger.warning(
                    "Boundary refine: failed to upsert ModelCall: %s", e
                )

        try:
            response = litellm.completion(
                model=self.config.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4096,
                timeout=self.config.openai_timeout,
                api_key=self.config.llm_api_key,
                base_url=self.config.openai_base_url,
            )

            choice = response.choices[0] if response.choices else None
            content = ""
            if choice:
                # Prefer chat content; fall back to text for completion-style responses
                content = (
                    getattr(getattr(choice, "message", None), "content", None) or ""
                )
                if not content:
                    content = getattr(choice, "text", "") or ""
            raw_response = content
            self.logger.debug(
                "LLM response received",
                extra={
                    "model": self.config.llm_model,
                    "content_preview": content[:200],
                },
            )
            # Full response for debugging parse issues; remove or redact if noisy.
            raw_preview = content[:1000]
            self.logger.debug(
                "LLM response raw (%s chars, preview up to 1000): %r",
                len(content),
                raw_preview,
                extra={"model": self.config.llm_model},
            )
            # Log the full response object so provider quirks are visible.
            try:
                response_payload = (
                    response.model_dump()
                    if hasattr(response, "model_dump")
                    else response
                )
                self.logger.debug(
                    "LLM full response object",
                    extra={"response_payload": response_payload},
                )
            except Exception:  # noqa: BLE001
                self.logger.debug("LLM full response object unavailable", exc_info=True)
            # Persist the raw response immediately so it's available even if parsing fails.
            self._update_model_call(
                model_call_id,
                status="received_response",
                response=raw_response,
                error_message=None,
            )
            # Parse JSON (strip markdown fences). Log parse diagnostics so failures are actionable.
            cleaned = re.sub(r"```json|```", "", content.strip())
            json_candidates = re.findall(r"\{.*?\}", cleaned, re.DOTALL)
            parse_error: str | None = None
            parsed: dict[str, Any] | None = None

            for candidate in json_candidates:
                try:
                    parsed = json.loads(candidate)
                    break
                except (
                    Exception  # noqa: BLE001
                ) as exc:  # capture the last parse error for logging
                    parse_error = str(exc)

            if parsed:
                refined = self._validate(
                    ad_start,
                    ad_end,
                    BoundaryRefinement(
                        refined_start=float(parsed["refined_start"]),
                        refined_end=float(parsed["refined_end"]),
                        start_adjustment_reason=parsed.get(
                            "start_adjustment_reason", parsed.get("start_reason", "")
                        ),
                        end_adjustment_reason=parsed.get(
                            "end_adjustment_reason", parsed.get("end_reason", "")
                        ),
                    ),
                )
                self._update_model_call(
                    model_call_id,
                    status="success",
                    response=raw_response,
                    error_message=None,
                )
                self.logger.info(
                    "LLM refinement applied",
                    extra={
                        "refined_start": refined.refined_start,
                        "refined_end": refined.refined_end,
                    },
                )
                return refined

            self.logger.warning(
                "Boundary refinement LLM response had no parseable JSON; falling back to heuristic",
                extra={
                    "model_call_id": model_call_id,
                    "ad_start": ad_start,
                    "ad_end": ad_end,
                    "json_candidate_count": len(json_candidates),
                    "parse_error": parse_error,
                    "first_candidate_preview": (
                        json_candidates[0][:200] if json_candidates else None
                    ),
                    "content_preview": (content or "")[:200],
                    "raw_response": raw_response,
                    "raw_response_len": len(content),
                },
            )
            # Also emit the raw response in-band so it shows up in plain-text logs.
            self.logger.debug(
                "Boundary refinement raw response (len=%s): %r",
                len(content),
                raw_preview,
                extra={"model_call_id": model_call_id},
            )
            self._update_model_call(
                model_call_id,
                status="success_heuristic",
                response=raw_response,
                error_message=parse_error or "parse_failed",
            )
        except Exception as e:  # noqa: BLE001
            self._update_model_call(
                model_call_id,
                status="failed_permanent",
                response=raw_response,
                error_message=str(e),
            )
            self.logger.warning(f"LLM refinement failed: {e}, using heuristic")

        # Fallback: heuristic refinement
        return self._heuristic_refine(ad_start, ad_end, context)

    def _update_model_call(
        self,
        model_call_id: int | None,
        *,
        status: str,
        response: str | None,
        error_message: str | None,
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
        except Exception as exc:  # best-effort; do not block refinement  # noqa: BLE001
            self.logger.warning(
                "Boundary refine: failed to update ModelCall %s: %s",
                model_call_id,
                exc,
            )

    def _get_context(
        self, ad_start: float, ad_end: float, all_segments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Get ±8 segments around ad"""
        ad_segs = [s for s in all_segments if ad_start <= s["start_time"] <= ad_end]
        if not ad_segs:
            return []

        first_idx = all_segments.index(ad_segs[0])
        last_idx = all_segments.index(ad_segs[-1])

        start_idx = max(0, first_idx - 8)
        end_idx = min(len(all_segments), last_idx + 9)

        return all_segments[start_idx:end_idx]

    def _heuristic_refine(
        self, ad_start: float, ad_end: float, context: list[dict[str, Any]]
    ) -> BoundaryRefinement:
        """Simple pattern-based refinement"""
        intro_patterns = ["brought to you", "sponsor", "let me tell you"]
        outro_patterns = [".com", "thanks to", "use code", "visit"]
=======
            max_start_extension=MAX_START_EXTENSION_SECONDS,
            max_end_extension=MAX_END_EXTENSION_SECONDS,
        )

        model_call = _get_or_create_refinement_model_call(
            config=self.config,
            db_session=self.db_session,
            model_call_query=self.model_call_query,
            model_name_suffix="::boundary-refinement",
            post_id=post_id,
            first_seq_num=first_seq_num,
            last_seq_num=last_seq_num,
            prompt=prompt,
        )

        if isinstance(self.config.whisper, TestWhisperConfig):
            heuristic = self._heuristic_refine(ad_start, ad_end, context)
            _update_refinement_model_call(
                db_session=self.db_session,
                model_call=model_call,
                status="success_heuristic",
                response=None,
                error_message="test_mode",
            )
            return heuristic

        try:
            response = litellm.completion(
                **_build_completion_args(
                    config=self.config, prompt=prompt, max_tokens=2048
                )
            )
            content = _extract_completion_content(response)
            parsed = self._parse_json(content)
            if parsed is None:
                heuristic = self._heuristic_refine(ad_start, ad_end, context)
                _update_refinement_model_call(
                    db_session=self.db_session,
                    model_call=model_call,
                    status="success_heuristic",
                    response=content,
                    error_message="parse_failed",
                )
                return heuristic

            refined = BoundaryRefinement(
                refined_start=float(parsed.get("refined_start", ad_start)),
                refined_end=float(parsed.get("refined_end", ad_end)),
                start_adjustment_reason=str(
                    parsed.get("start_adjustment_reason")
                    or parsed.get("start_reason")
                    or "llm_refinement"
                ),
                end_adjustment_reason=str(
                    parsed.get("end_adjustment_reason")
                    or parsed.get("end_reason")
                    or "llm_refinement"
                ),
                confidence_adjustment=float(parsed.get("confidence_adjustment", 0.0)),
            )
            refined = self._validate(ad_start, ad_end, refined)
            _update_refinement_model_call(
                db_session=self.db_session,
                model_call=model_call,
                status="success",
                response=content,
                error_message=None,
            )
            return refined
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.warning("Boundary refinement failed: %s", exc)
            heuristic = self._heuristic_refine(ad_start, ad_end, context)
            _update_refinement_model_call(
                db_session=self.db_session,
                model_call=model_call,
                status="failed_permanent",
                response=None,
                error_message=str(exc),
            )
            return heuristic

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        cleaned = re.sub(r"```json|```", "", (content or "").strip())
        json_candidates = re.findall(r"\{.*?\}", cleaned, re.DOTALL)
        for candidate in json_candidates:
            try:
                loaded = json.loads(candidate)
            except Exception:
                continue
            if isinstance(loaded, dict):
                return loaded
        return None

    def _get_context(
        self,
        ad_start: float,
        ad_end: float,
        all_segments: List[Dict[str, Any]],
        *,
        first_seq_num: Optional[int],
        last_seq_num: Optional[int],
    ) -> List[Dict[str, Any]]:
        if first_seq_num is not None and last_seq_num is not None:
            selected = [
                segment
                for segment in all_segments
                if first_seq_num - 2
                <= int(segment.get("sequence_num", -1))
                <= last_seq_num + 2
            ]
            if selected:
                return selected

        overlapping = [
            segment
            for segment in all_segments
            if float(segment.get("start_time", 0.0)) <= ad_end
            and float(segment.get("end_time", 0.0)) >= ad_start
        ]
        if not overlapping:
            return []

        first_index = all_segments.index(overlapping[0])
        last_index = all_segments.index(overlapping[-1])
        start_index = max(0, first_index - 8)
        end_index = min(len(all_segments), last_index + 9)
        return all_segments[start_index:end_index]

    def _heuristic_refine(
        self, ad_start: float, ad_end: float, context: List[Dict[str, Any]]
    ) -> BoundaryRefinement:
        intro_patterns = [
            "brought to you",
            "word from our sponsor",
            "sponsor today",
            "let me tell you about",
            "before we continue",
        ]
        outro_patterns = [
            "use code",
            "visit",
            "thanks to",
            "back to the show",
            "and we're back",
        ]
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

        refined_start = ad_start
        refined_end = ad_end

<<<<<<< HEAD
        # Check before ad for intros
        for seg in context:
            if seg["start_time"] < ad_start:
                if any(p in seg["text"].lower() for p in intro_patterns):
                    self.logger.debug(
                        "Intro pattern matched",
                        extra={
                            "matched_text": seg["text"],
                            "start_time": seg["start_time"],
                        },
                    )
                    refined_start = seg["start_time"]

        # Check after ad for outros
        for seg in context:
            if seg["start_time"] > ad_end:
                if any(p in seg["text"].lower() for p in outro_patterns):
                    self.logger.debug(
                        "Outro pattern matched",
                        extra={
                            "matched_text": seg["text"],
                            "start_time": seg["start_time"],
                        },
                    )
                    refined_end = seg.get("end_time", seg["start_time"] + 5.0)

        result = BoundaryRefinement(
            refined_start,
            refined_end,
            "heuristic",
            "heuristic",
        )
        self.logger.info(
            "Heuristic refinement applied",
            extra={
                "refined_start": result.refined_start,
                "refined_end": result.refined_end,
            },
        )
        return result

    def _validate(
        self, orig_start: float, orig_end: float, refinement: BoundaryRefinement
    ) -> BoundaryRefinement:
        """Constrain refinement to reasonable bounds"""
        max_start_ext = MAX_START_EXTENSION_SECONDS
        max_end_ext = MAX_END_EXTENSION_SECONDS

        refinement.refined_start = max(
            refinement.refined_start, orig_start - max_start_ext
        )
        refinement.refined_end = min(refinement.refined_end, orig_end + max_end_ext)
        if refinement.refined_start >= refinement.refined_end:
            refinement.refined_start = orig_start
            refinement.refined_end = orig_end

        self.logger.debug(
            "Refinement validated",
            extra={
                "orig_start": orig_start,
                "orig_end": orig_end,
                "refined_start": refinement.refined_start,
                "refined_end": refinement.refined_end,
            },
        )

=======
        for segment in context:
            text = str(segment.get("text", "")).lower()
            segment_start = float(segment.get("start_time", ad_start))
            segment_end = float(segment.get("end_time", ad_end))
            if segment_start < ad_start and any(
                pattern in text for pattern in intro_patterns
            ):
                refined_start = min(refined_start, segment_start)
            if segment_start > ad_end and any(
                pattern in text for pattern in outro_patterns
            ):
                refined_end = max(refined_end, segment_end)

        return self._validate(
            ad_start,
            ad_end,
            BoundaryRefinement(
                refined_start=refined_start,
                refined_end=refined_end,
                start_adjustment_reason="heuristic",
                end_adjustment_reason="heuristic",
            ),
        )

    def _validate(
        self,
        orig_start: float,
        orig_end: float,
        refinement: BoundaryRefinement,
    ) -> BoundaryRefinement:
        refinement.refined_start = max(
            refinement.refined_start,
            orig_start - MAX_START_EXTENSION_SECONDS,
        )
        refinement.refined_end = min(
            refinement.refined_end,
            orig_end + MAX_END_EXTENSION_SECONDS,
        )
        if refinement.refined_end <= refinement.refined_start:
            refinement.refined_start = orig_start
            refinement.refined_end = orig_end
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        return refinement
