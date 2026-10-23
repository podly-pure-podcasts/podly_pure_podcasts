"""Refuse a silent 0-ad miss when Whisper already shows opening ad cues.

Permanent LLM failures (truncated/unusable output after retries, content
filter) raise ClassificationIncompleteError and publish the unprocessed
episode with a notice clip. This guard covers the remaining case: classify
returned 0 ads after successful LLM calls, but the opening transcript still
has strong commercial cues.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from podcast_processor.cue_detector import CueDetector

OPENING_WINDOW_SECONDS = 180.0
# Strong commercial cues, including scout extras the user named
# ("brought to you by") without changing production CueDetector defaults.
GUARD_CUE_KEYS: tuple[str, ...] = ("url", "promo", "phone", "cta", "sponsor")


@dataclass(frozen=True)
class OpeningCue:
    start_time: float
    end_time: float
    text: str
    signals: dict[str, bool]


def _segment_times_and_text(segment: Any) -> tuple[float, float, str]:
    start = float(getattr(segment, "start_time", getattr(segment, "start", 0.0)) or 0.0)
    end = float(getattr(segment, "end_time", getattr(segment, "end", start)) or start)
    text = str(getattr(segment, "text", "") or "")
    return start, end, text


def collect_opening_ad_cues(
    segments: list[Any],
    *,
    first_seconds: float = OPENING_WINDOW_SECONDS,
) -> list[OpeningCue]:
    """Return strong ad-cue hits in the first `first_seconds` of transcript."""
    detector = CueDetector(include_scout_extras=True)
    hits: list[OpeningCue] = []
    for segment in segments:
        start, end, text = _segment_times_and_text(segment)
        if start >= first_seconds:
            continue
        signals = detector.analyze(text)
        if any(signals.get(key, False) for key in GUARD_CUE_KEYS):
            hits.append(
                OpeningCue(
                    start_time=start,
                    end_time=end,
                    text=text.strip(),
                    signals={key: bool(signals.get(key)) for key in GUARD_CUE_KEYS},
                )
            )
    return hits


def ad_detection_confidence_failure(
    *,
    n_ad_segments: int,
    opening_cues: list[OpeningCue],
    n_failed_classify_calls: int,
    n_success_classify_calls: int,
    first_seconds: float = OPENING_WINDOW_SECONDS,
) -> str | None:
    """Return a job-failure message if publishing 0 ads would be a silent miss.

    Returns None when it is acceptable to publish (including true ad-free
    episodes with successful classify and no opening cues).
    """
    if n_ad_segments > 0:
        return None

    if n_failed_classify_calls > 0 and n_success_classify_calls == 0:
        return (
            "Ad classification failed for every LLM chunk and 0 ads were labeled. "
            "Refusing to publish an uncut file as success."
        )

    if opening_cues:
        examples = "; ".join(
            f"{cue.start_time:.1f}s {cue.text[:80]!r}" for cue in opening_cues[:3]
        )
        return (
            f"Opening transcript has {len(opening_cues)} strong ad cue(s) in the first "
            f"{int(first_seconds)}s but detector returned 0 ads. "
            f"Refusing to publish a clean file. Examples: {examples}"
        )

    return None
