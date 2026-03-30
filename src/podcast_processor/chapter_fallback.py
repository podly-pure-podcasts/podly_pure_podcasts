"""Resolve and generate chapter metadata for the LLM processing path."""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Sequence
from typing import Any

import litellm

from podcast_processor.chapter_reader import Chapter, read_chapters
from podcast_processor.description_chapter_parser import parse_chapters_from_description
from podcast_processor.llm_model_call_utils import (
    extract_litellm_content,
    extract_litellm_finish_reason,
    extract_litellm_usage,
)
from podcast_processor.word_boundary_refiner import WordBoundaryRefiner
from shared.llm_utils import model_uses_max_completion_tokens

logger = logging.getLogger("global_logger")

# Enough room for compact JSON chapter plans without inviting verbose responses.
TOPIC_CHAPTER_LLM_MAX_OUTPUT_TOKENS = 4096
# Aim for about 60 transcript blocks so long episodes still fit in one prompt.
TOPIC_CHAPTER_TARGET_BLOCK_COUNT = 60
# One-minute blocks are the minimum useful granularity before prompt size balloons.
TOPIC_CHAPTER_MIN_BLOCK_SECONDS = 60
# Two-minute blocks are the largest window we allow before chapter starts get too coarse.
TOPIC_CHAPTER_MAX_BLOCK_SECONDS = 2 * 60
# Keep only a short snippet per block; ~220 chars is enough topic signal for the LLM.
TOPIC_CHAPTER_MAX_CHARS_PER_BLOCK = 220
# For long episodes, cap chapter counts to roughly one chapter every five minutes.
TOPIC_CHAPTER_CAP_WINDOW_SECONDS = 5 * 60
# Treat episodes under an hour as "short" when applying the hard chapter-count cap.
TOPIC_CHAPTER_SHORT_EPISODE_SECONDS = 60 * 60
# Short episodes top out at 10 chapters to avoid noisy over-segmentation.
TOPIC_CHAPTER_SHORT_EPISODE_CAP = 10
# Retry prompts keep one overlapping block so truncated responses retain local context.
TOPIC_CHAPTER_RETRY_OVERLAP_BLOCKS = 1


def resolve_llm_path_chapters(
    *,
    unprocessed_audio_path: str | None,
    description: str | None,
    transcript_segments: Sequence[Any],
    logger_override: logging.Logger | None = None,
) -> tuple[list[Chapter], str]:
    """
    Resolve chapter metadata for the LLM path using a fallback chain.

    Order:
    1) Embedded MP3 chapters
    2) Parsed description timestamps
    3) Generated transcript-based chapters
    """
    log = logger_override or logger

    if unprocessed_audio_path:
        embedded = read_chapters(unprocessed_audio_path)
        if embedded:
            log.info("Resolved %d chapters from embedded MP3 metadata", len(embedded))
            return embedded, "embedded"

    transcript_duration_ms = _transcript_duration_ms(transcript_segments)

    parsed = parse_chapters_from_description(
        description,
        total_duration_ms=transcript_duration_ms,
    )
    if parsed:
        log.info("Resolved %d chapters from episode description", len(parsed))
        return parsed, "description"

    generated = generate_chapters_from_transcript(
        transcript_segments,
        total_duration_ms=transcript_duration_ms,
    )
    if generated:
        log.info("Generated %d chapters from transcript", len(generated))
        return generated, "transcript"

    log.info("No chapters available from embedded metadata, description, or transcript")
    return [], "none"


def refine_description_chapters_with_word_refiner(
    chapters: Sequence[Chapter],
    transcript_segments: Sequence[Any],
    *,
    config: Any,
    logger_override: logging.Logger | None = None,
    max_shift_seconds: float = 90.0,
) -> list[Chapter]:
    """
    Refine description-derived chapter start times using transcript phrase matching.

    This reuses the same heuristic phrase-timing logic as the word-level boundary
    refiner (but does not invoke any extra LLM calls).
    """
    log = logger_override or logger
    if not chapters or not transcript_segments:
        return list(chapters)
    if not getattr(config, "enable_word_level_boundary_refiner", False):
        return list(chapters)

    all_segments = _segments_for_word_refiner(transcript_segments)
    if not all_segments:
        return list(chapters)

    refiner_logger = log if isinstance(log, logging.Logger) else None
    refiner = WordBoundaryRefiner(config=config, logger=refiner_logger)
    max_shift_ms = max(0, int(max_shift_seconds * 1000))

    sorted_chapters = sorted(list(chapters), key=lambda ch: ch.start_time_ms)
    candidate_starts_ms: list[int] = []
    refined_count = 0

    for chapter in sorted_chapters:
        original_start_ms = int(chapter.start_time_ms)
        preferred_seq = _nearest_segment_seq_for_time(all_segments, original_start_ms)
        context_segments = _context_segments_around_time(
            all_segments,
            time_seconds=original_start_ms / 1000.0,
            window_seconds=60.0,
        )
        estimated_start = refiner._estimate_phrase_time(
            all_segments=all_segments,
            context_segments=context_segments,
            preferred_segment_seq=preferred_seq,
            phrase=chapter.title,
            direction="start",
        )

        new_start_ms = original_start_ms
        if estimated_start is not None:
            candidate_ms = round(float(estimated_start) * 1000.0)
            if abs(candidate_ms - original_start_ms) <= max_shift_ms:
                new_start_ms = candidate_ms

        candidate_starts_ms.append(new_start_ms)
        if new_start_ms != original_start_ms:
            refined_count += 1

    # Enforce monotonic starts and rebuild end times from the next start.
    adjusted: list[Chapter] = []
    last_start_ms = -1
    for idx, chapter in enumerate(sorted_chapters):
        start_ms = max(candidate_starts_ms[idx], last_start_ms + 1 if adjusted else 0)
        if idx + 1 < len(sorted_chapters):
            next_candidate = candidate_starts_ms[idx + 1]
            end_ms = max(start_ms, next_candidate)
        else:
            end_ms = max(start_ms, int(chapter.end_time_ms))

        adjusted.append(
            Chapter(
                element_id=chapter.element_id,
                title=chapter.title,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
            )
        )
        last_start_ms = start_ms

    if refined_count > 0:
        log.info(
            "Refined %d description chapter boundary starts using word-level "
            "refiner heuristics",
            refined_count,
        )
    return adjusted


def refine_transcript_chapters_with_word_refiner(
    chapters: Sequence[Chapter],
    transcript_segments: Sequence[Any],
    *,
    config: Any,
    logger_override: Any = None,
    max_shift_seconds: float = 5 * 60,
) -> list[Chapter]:
    """
    Pull coarse transcript-generated chapter starts back to matching transcript text.

    Topic chapters are generated from coarse transcript blocks, so their chosen block
    can lag behind the actual first mention of the topic by a couple of minutes on
    long episodes. This reuses the word-level phrase matcher locally to tighten the
    start timestamp without making any extra LLM calls.
    """
    log = logger_override or logger
    if not chapters or not transcript_segments:
        return list(chapters)

    all_segments = _segments_for_word_refiner(transcript_segments)
    if not all_segments:
        return list(chapters)

    refiner_logger = log if isinstance(log, logging.Logger) else None
    refiner = WordBoundaryRefiner(config=config, logger=refiner_logger)
    max_shift_ms = max(0, int(max_shift_seconds * 1000))
    context_window_seconds = max(60.0, float(max_shift_seconds))

    sorted_chapters = sorted(list(chapters), key=lambda ch: ch.start_time_ms)
    candidate_starts_ms: list[int] = []
    refined_count = 0

    for idx, chapter in enumerate(sorted_chapters):
        original_start_ms = int(chapter.start_time_ms)
        if idx == 0:
            candidate_starts_ms.append(original_start_ms)
            continue

        context_segments = _context_segments_around_time(
            all_segments,
            time_seconds=original_start_ms / 1000.0,
            window_seconds=context_window_seconds,
        )
        estimated_start = refiner._estimate_phrase_time(
            all_segments=all_segments,
            context_segments=context_segments,
            preferred_segment_seq=None,
            phrase=chapter.title,
            direction="start",
        )

        new_start_ms = original_start_ms
        if estimated_start is not None:
            candidate_ms = round(float(estimated_start) * 1000.0)
            if (
                candidate_ms <= original_start_ms
                and (original_start_ms - candidate_ms) <= max_shift_ms
            ):
                new_start_ms = candidate_ms

        candidate_starts_ms.append(new_start_ms)
        if new_start_ms != original_start_ms:
            refined_count += 1

    adjusted: list[Chapter] = []
    last_start_ms = -1
    for idx, chapter in enumerate(sorted_chapters):
        start_ms = max(candidate_starts_ms[idx], last_start_ms + 1 if adjusted else 0)
        if idx + 1 < len(sorted_chapters):
            next_candidate = candidate_starts_ms[idx + 1]
            end_ms = max(start_ms, next_candidate)
        else:
            end_ms = max(start_ms, int(chapter.end_time_ms))

        adjusted.append(
            Chapter(
                element_id=chapter.element_id,
                title=chapter.title,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
            )
        )
        last_start_ms = start_ms

    if refined_count > 0:
        log.info(
            "Refined %d transcript topic chapter boundary starts using word-level "
            "phrase matching",
            refined_count,
        )
    return adjusted


def generate_chapters_from_transcript(
    transcript_segments: Sequence[Any],
    *,
    total_duration_ms: int | None = None,
    target_chapter_seconds: int = 8 * 60,
    min_remaining_seconds_for_split: int = 3 * 60,
) -> list[Chapter]:
    """
    Generate coarse chapters from transcript segments using time windows.

    This is an MVP heuristic fallback intended to guarantee usable chapters.
    """
    if not transcript_segments:
        return []

    segments = list(transcript_segments)
    segments.sort(key=_seg_start_ms)

    if total_duration_ms is None:
        total_duration_ms = _transcript_duration_ms(segments)

    if total_duration_ms is None:
        return []

    boundaries: list[int] = []
    boundary_titles: list[str] = []

    current_boundary_ms = _seg_start_ms(segments[0])
    boundaries.append(current_boundary_ms)
    boundary_titles.append(_chapter_title_from_segment(segments[0], 1))

    for seg in segments[1:]:
        seg_start_ms = _seg_start_ms(seg)
        elapsed_sec = (seg_start_ms - current_boundary_ms) / 1000.0
        remaining_sec = max(0.0, (total_duration_ms - seg_start_ms) / 1000.0)

        if elapsed_sec < target_chapter_seconds:
            continue

        if remaining_sec and remaining_sec < min_remaining_seconds_for_split:
            continue

        if seg_start_ms <= boundaries[-1]:
            continue

        boundaries.append(seg_start_ms)
        boundary_titles.append(
            _chapter_title_from_segment(seg, len(boundary_titles) + 1)
        )
        current_boundary_ms = seg_start_ms

    chapters: list[Chapter] = []
    for index, start_ms in enumerate(boundaries):
        end_ms = (
            boundaries[index + 1] if index + 1 < len(boundaries) else total_duration_ms
        )
        chapters.append(
            Chapter(
                element_id=f"gen{index}",
                title=boundary_titles[index],
                start_time_ms=start_ms,
                end_time_ms=max(start_ms, end_ms),
            )
        )

    return chapters


def _segments_for_word_refiner(
    transcript_segments: Sequence[Any],
) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for idx, seg in enumerate(sorted(list(transcript_segments), key=_seg_start_ms)):
        try:
            sequence_num = int(seg.sequence_num)
        except Exception:  # noqa: BLE001
            sequence_num = idx
        try:
            start_time = float(getattr(seg, "start_time", 0.0))
        except Exception:  # noqa: BLE001
            start_time = 0.0
        try:
            end_time = float(getattr(seg, "end_time", start_time))
        except Exception:  # noqa: BLE001
            end_time = start_time

        segments.append(
            {
                "sequence_num": sequence_num,
                "start_time": start_time,
                "end_time": max(start_time, end_time),
                "text": str(getattr(seg, "text", "") or ""),
            }
        )
    return segments


def _nearest_segment_seq_for_time(
    all_segments: Sequence[dict[str, Any]],
    time_ms: int,
) -> int | None:
    if not all_segments:
        return None

    time_seconds = float(time_ms) / 1000.0
    best: tuple[float, int] | None = None
    for seg in all_segments:
        start_time = float(seg.get("start_time", 0.0))
        end_time = float(seg.get("end_time", start_time))
        if start_time <= time_seconds <= end_time:
            return int(seg.get("sequence_num", 0))

        distance = min(abs(time_seconds - start_time), abs(time_seconds - end_time))
        seq = int(seg.get("sequence_num", 0))
        if best is None or distance < best[0]:
            best = (distance, seq)
    return best[1] if best is not None else None


def _context_segments_around_time(
    all_segments: Sequence[dict[str, Any]],
    *,
    time_seconds: float,
    window_seconds: float,
) -> list[dict[str, Any]]:
    if not all_segments:
        return []
    start_time = float(time_seconds) - max(0.0, float(window_seconds))
    end_time = float(time_seconds) + max(0.0, float(window_seconds))

    selected: list[dict[str, Any]] = []
    for seg in all_segments:
        seg_start = float(seg.get("start_time", 0.0))
        seg_end = float(seg.get("end_time", seg_start))
        if seg_end >= start_time and seg_start <= end_time:
            selected.append(dict(seg))
    return selected or [dict(all_segments[0])]


def refine_generated_chapter_titles_with_llm(
    chapters: list[Chapter],
    transcript_segments: Sequence[Any],
    *,
    llm_model: str | None,
    llm_api_key: str | None = None,
    openai_base_url: str | None = None,
    openai_timeout_sec: int = 300,
    logger_override: logging.Logger | None = None,
) -> list[Chapter]:
    """
    Refine transcript-generated chapter titles via a single batched LLM call.

    Falls back to the original titles on any error.
    """
    log = logger_override or logger
    if not chapters or not transcript_segments or not llm_model:
        return chapters

    prompt = _build_chapter_title_refinement_prompt(chapters, transcript_segments)
    if not prompt:
        return chapters

    completion_args: dict[str, Any] = {
        "model": llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write concise podcast chapter titles. Return valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "timeout": int(openai_timeout_sec or 300),
        "api_key": llm_api_key,
        "base_url": openai_base_url,
    }
    if model_uses_max_completion_tokens(llm_model):
        completion_args["max_completion_tokens"] = 300
    else:
        completion_args["max_tokens"] = 300

    try:
        response = litellm.completion(**completion_args)
        content = extract_litellm_content(response)
        refined_titles = _parse_refined_titles_response(content)
        if not refined_titles:
            return chapters

        updated: list[Chapter] = []
        for i, chapter in enumerate(chapters):
            title = refined_titles.get(i, "").strip() or chapter.title
            updated.append(
                Chapter(
                    element_id=chapter.element_id,
                    title=title,
                    start_time_ms=chapter.start_time_ms,
                    end_time_ms=chapter.end_time_ms,
                )
            )
        log.info(
            "Refined %d transcript-generated chapter titles via LLM",
            len(updated),
        )
        return updated
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "LLM chapter title refinement failed; using heuristic titles: %s",
            exc,
        )
        return chapters


def generate_topic_chapters_from_transcript_with_llm(
    transcript_segments: Sequence[Any],
    *,
    llm_model: str | None,
    llm_api_key: str | None = None,
    openai_base_url: str | None = None,
    total_duration_ms: int | None = None,
    openai_timeout_sec: int = 300,
    target_chapter_seconds: int = 8 * 60,
    min_chapter_seconds: int = 2 * 60,
    logger_override: logging.Logger | None = None,
) -> list[Chapter]:
    """
    Generate transcript chapters with topic-based boundaries via an LLM call.

    May perform one continuation retry for remaining blocks after salvaging a
    truncated partial response. Falls back to [] on parsing/model failure so the
    caller can use heuristics.
    """
    log = logger_override or logger
    if not transcript_segments or not llm_model:
        return []

    segments = sorted(list(transcript_segments), key=_seg_start_ms)
    if not segments:
        return []

    if total_duration_ms is None:
        total_duration_ms = _transcript_duration_ms(segments)
    if total_duration_ms is None or total_duration_ms <= 0:
        return []

    blocks = _build_topic_blocks(
        segments,
        total_duration_ms=total_duration_ms,
        target_block_count=TOPIC_CHAPTER_TARGET_BLOCK_COUNT,
        min_block_seconds=TOPIC_CHAPTER_MIN_BLOCK_SECONDS,
        max_chars_per_block=TOPIC_CHAPTER_MAX_CHARS_PER_BLOCK,
    )
    if not blocks:
        log.warning(
            "LLM topic chapter generation skipped: no transcript blocks built "
            "(segments=%d)",
            len(segments),
        )
        return []

    log.info(
        "Attempting topic-based transcript chapter generation via LLM "
        "(segments=%d, blocks=%d, target_blocks=%d, max_chars_per_block=%d)",
        len(segments),
        len(blocks),
        TOPIC_CHAPTER_TARGET_BLOCK_COUNT,
        TOPIC_CHAPTER_MAX_CHARS_PER_BLOCK,
    )

    prompt = _build_topic_chapter_generation_prompt(
        blocks=blocks,
        total_duration_ms=total_duration_ms,
        target_chapter_seconds=target_chapter_seconds,
        min_chapter_seconds=min_chapter_seconds,
    )
    if not prompt:
        return []
    log.info(
        "Topic chapter prompt built (chars=%d, blocks=%d)",
        len(prompt),
        len(blocks),
    )

    try:
        parsed, content, finish_reason, expected_count = _request_topic_chapter_plan(
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            openai_base_url=openai_base_url,
            prompt=prompt,
            openai_timeout_sec=openai_timeout_sec,
            logger_override=log,
            phase_label="Topic chapter",
        )
        if not parsed:
            log.warning(
                "LLM topic chapter generation returned no parseable chapter plan; "
                "falling back to heuristic transcript boundaries. "
                "response_snippet=%r",
                _truncate_for_log(content),
            )
            return []

        merged_plan = _retry_incomplete_topic_chapter_plan(
            initial_plan=parsed,
            initial_expected_count=expected_count,
            initial_finish_reason=finish_reason,
            blocks=blocks,
            total_duration_ms=total_duration_ms,
            target_chapter_seconds=target_chapter_seconds,
            min_chapter_seconds=min_chapter_seconds,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            openai_base_url=openai_base_url,
            openai_timeout_sec=openai_timeout_sec,
            logger_override=log,
        )

        chapters = _chapters_from_topic_plan(
            merged_plan,
            blocks=blocks,
            total_duration_ms=total_duration_ms,
            min_chapter_gap_ms=int(min_chapter_seconds * 1000),
        )
        if not chapters:
            log.warning(
                "LLM topic chapter plan was unusable after validation; "
                "falling back to heuristic transcript boundaries "
                "(parsed_items=%d)",
                len(merged_plan),
            )
            return []

        log.info(
            "Generated %d topic-based transcript chapters via LLM",
            len(chapters),
        )
        return chapters
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "LLM topic chapter generation failed; using heuristic split: %s",
            exc,
        )
        return []


def _transcript_duration_ms(transcript_segments: Sequence[Any]) -> int | None:
    if not transcript_segments:
        return None
    end_times_ms = [_seg_end_ms(seg) for seg in transcript_segments]
    if not end_times_ms:
        return None
    max_end_ms = max(end_times_ms)
    return max_end_ms if max_end_ms > 0 else None


def _seg_start_ms(segment: Any) -> int:
    return int(float(getattr(segment, "start_time", 0.0)) * 1000)


def _seg_end_ms(segment: Any) -> int:
    return int(float(getattr(segment, "end_time", 0.0)) * 1000)


def _chapter_title_from_segment(segment: Any, index: int) -> str:
    text = str(getattr(segment, "text", "") or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[^\w]+", "", text)
    if not text:
        return f"Chapter {index}"

    words = text.split(" ")
    title = " ".join(words[:8]).strip(" -:,.")
    if not title:
        return f"Chapter {index}"
    if len(words) > 8:
        title = f"{title}..."
    return title


def _chapter_title_from_text(text: str, index: int) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    normalized = re.sub(r"^[^\w]+", "", normalized)
    if not normalized:
        return f"Chapter {index}"

    words = normalized.split(" ")
    title = " ".join(words[:8]).strip(" -:,.")
    if not title:
        return f"Chapter {index}"
    if len(words) > 8:
        title = f"{title}..."
    return title


def _build_chapter_title_refinement_prompt(
    chapters: list[Chapter],
    transcript_segments: Sequence[Any],
) -> str:
    segments = sorted(list(transcript_segments), key=_seg_start_ms)
    if not segments:
        return ""

    payload: list[dict[str, Any]] = []
    for i, chapter in enumerate(chapters):
        snippet = _chapter_snippet_text(chapter, segments)
        payload.append(
            {
                "index": i,
                "start_timestamp": _format_timestamp(chapter.start_time_ms),
                "current_title": chapter.title,
                "snippet": snippet,
            }
        )

    return (
        "Rewrite the chapter titles to be clearer and more useful.\n"
        "Rules:\n"
        '- Return JSON object only: {"titles": [{"index": 0, "title": "..."}]}\n'
        "- Keep titles factual and concise (3-8 words preferred)\n"
        "- No quotes, no punctuation unless needed\n"
        "- Preserve chapter order and count\n\n"
        f"Chapters:\n{json.dumps(payload, ensure_ascii=True)}"
    )


def _chapter_snippet_text(chapter: Chapter, segments: Sequence[Any]) -> str:
    start_ms = chapter.start_time_ms
    end_ms = chapter.end_time_ms
    snippets: list[str] = []
    total_chars = 0

    for seg in segments:
        seg_start = _seg_start_ms(seg)
        seg_end = _seg_end_ms(seg)
        overlaps = seg_end > start_ms and seg_start < end_ms
        if not overlaps:
            continue
        text = re.sub(r"\s+", " ", str(getattr(seg, "text", "") or "")).strip()
        if not text:
            continue
        snippets.append(text)
        total_chars += len(text)
        if len(snippets) >= 6 or total_chars >= 700:
            break

    return " ".join(snippets).strip()


def _build_topic_blocks(
    transcript_segments: Sequence[Any],
    *,
    total_duration_ms: int,
    target_block_count: int = TOPIC_CHAPTER_TARGET_BLOCK_COUNT,
    min_block_seconds: int = TOPIC_CHAPTER_MIN_BLOCK_SECONDS,
    max_block_seconds: int = TOPIC_CHAPTER_MAX_BLOCK_SECONDS,
    max_chars_per_block: int = TOPIC_CHAPTER_MAX_CHARS_PER_BLOCK,
) -> list[dict[str, Any]]:
    if not transcript_segments:
        return []

    # Aim for a bounded prompt size by grouping transcript into ~60 coarse blocks,
    # but never let long episodes drift past a 2-minute timing window.
    raw_window_ms = max(1, total_duration_ms // max(1, target_block_count))
    min_block_ms = max(1, min_block_seconds * 1000)
    max_block_ms = max(min_block_ms, max_block_seconds * 1000)
    block_window_ms = min(max_block_ms, max(min_block_ms, raw_window_ms))
    # Round to 30-second increments for cleaner boundaries.
    round_ms = 30_000
    block_window_ms = max(
        round_ms,
        ((block_window_ms + round_ms - 1) // round_ms) * round_ms,
    )
    block_window_ms = min(max_block_ms, block_window_ms)

    blocks: list[dict[str, Any]] = []
    current_start_ms: int | None = None
    current_end_ms: int | None = None
    current_text_parts: list[str] = []
    current_char_count = 0

    def flush_block() -> None:
        nonlocal current_start_ms, current_end_ms
        nonlocal current_text_parts, current_char_count
        if current_start_ms is None or current_end_ms is None:
            return
        text = " ".join(current_text_parts).strip()
        if not text:
            text = ""
        blocks.append(
            {
                "block_index": len(blocks),
                "start_ms": current_start_ms,
                "end_ms": max(current_start_ms, current_end_ms),
                "timestamp": _format_timestamp(current_start_ms),
                "text": text,
            }
        )
        current_start_ms = None
        current_end_ms = None
        current_text_parts = []
        current_char_count = 0

    for seg in transcript_segments:
        seg_start_ms = _seg_start_ms(seg)
        seg_end_ms = max(seg_start_ms, _seg_end_ms(seg))
        seg_text = re.sub(r"\s+", " ", str(getattr(seg, "text", "") or "")).strip()

        if current_start_ms is None:
            current_start_ms = seg_start_ms
            current_end_ms = seg_end_ms
        elif seg_start_ms - current_start_ms >= block_window_ms:
            flush_block()
            current_start_ms = seg_start_ms
            current_end_ms = seg_end_ms
        else:
            current_end_ms = max(int(current_end_ms or seg_end_ms), seg_end_ms)

        if not seg_text:
            continue

        remaining = max(0, max_chars_per_block - current_char_count)
        if remaining <= 0:
            continue
        clipped = seg_text[:remaining].strip()
        if not clipped:
            continue
        current_text_parts.append(clipped)
        current_char_count += len(clipped) + 1

    flush_block()

    # Remove empty blocks when possible; keep at least one.
    nonempty = [b for b in blocks if str(b.get("text") or "").strip()]
    return nonempty or blocks[:1]


def _build_topic_chapter_generation_prompt(
    *,
    blocks: list[dict[str, Any]],
    total_duration_ms: int,
    target_chapter_seconds: int,
    min_chapter_seconds: int,
    continuation_after_block_index: int | None = None,
    existing_chapter_starts: Sequence[int] | None = None,
) -> str:
    if not blocks:
        return ""

    duration_sec = max(1, total_duration_ms // 1000)
    target_count = max(1, round(duration_sec / max(60, target_chapter_seconds)))
    min_count = max(1, target_count - 2)
    max_count = max(min_count, min(12, target_count + 2))
    if duration_sec >= 20 * 60:
        min_count = max(2, min_count)
    hard_max_count = _topic_chapter_count_cap_for_duration(duration_sec)
    existing_start_indexes = sorted(
        {int(x) for x in (existing_chapter_starts or []) if int(x) >= 0}
    )
    is_continuation = continuation_after_block_index is not None
    if is_continuation:
        remaining_hard_max_count = max(0, hard_max_count - len(existing_start_indexes))
        if remaining_hard_max_count <= 0:
            return ""
        hard_max_count = remaining_hard_max_count
        min_count = max(1, min(min_count, hard_max_count))
        max_count = max(min_count, min(max_count, hard_max_count))
    else:
        min_count = min(min_count, hard_max_count)
        max_count = min(max_count, hard_max_count)

    payload = [
        {
            "block_index": int(block["block_index"]),
            "start_timestamp": str(block["timestamp"]),
            "text": str(block.get("text") or ""),
        }
        for block in blocks
    ]
    continuation_lines = ""
    if is_continuation and continuation_after_block_index is not None:
        continuation_lines = (
            "- This is a continuation request for remaining transcript blocks\n"
            f"- Return only chapters with block_index > {continuation_after_block_index}\n"
            "- chapter_count counts only chapters returned in this response\n"
            f"- Do not repeat existing chapter block_index values: "
            f"{json.dumps(existing_start_indexes, ensure_ascii=True)}\n"
        )

    first_chapter_rule = (
        "- First chapter must start at block_index 0\n" if not is_continuation else ""
    )

    return (
        "Create podcast chapters based on topic changes from transcript blocks.\n"
        "Do not split on fixed time intervals unless the topic clearly changes.\n"
        "Return minified JSON only on a single line (no markdown, no code fences, "
        "no extra text).\n"
        "Format: "
        '{"chapter_count":2,"chapters":[{"block_index":0,"title":"Intro"},'
        '{"block_index":5,"title":"Main topic"}]}\n'
        "Rules:\n"
        "- Put chapter_count first in the JSON object\n"
        "- chapter_count must equal the number of items in chapters\n"
        f"{first_chapter_rule}"
        f"{continuation_lines}"
        f"- Prefer {min_count}-{max_count} chapters for this episode length\n"
        f"- Hard cap: at most {hard_max_count} chapters total\n"
        "- The hard cap is a ceiling, not a target\n"
        f"- Avoid chapters shorter than about {min_chapter_seconds // 60} minutes "
        "unless intro/outro transitions justify it\n"
        "- Use only keys block_index and title for each chapter\n"
        "- Titles should be factual and concise (2-6 words preferred)\n"
        "- Preserve chronological order and do not repeat block_index\n\n"
        f"Episode duration: {_format_timestamp(total_duration_ms)}\n"
        f"Transcript blocks:\n{json.dumps(payload, ensure_ascii=True)}"
    )


def _request_topic_chapter_plan(
    *,
    llm_model: str,
    llm_api_key: str | None = None,
    openai_base_url: str | None = None,
    prompt: str,
    openai_timeout_sec: int,
    logger_override: logging.Logger | None = None,
    phase_label: str = "Topic chapter",
) -> tuple[list[tuple[int, str]], str, str | None, int | None]:
    log = logger_override or logger
    completion_args: dict[str, Any] = {
        "model": llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You identify topic transitions in podcast transcripts and return "
                    "valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "timeout": int(openai_timeout_sec or 300),
        "api_key": llm_api_key,
        "base_url": openai_base_url,
    }
    if model_uses_max_completion_tokens(llm_model):
        completion_args["max_completion_tokens"] = TOPIC_CHAPTER_LLM_MAX_OUTPUT_TOKENS
    else:
        completion_args["max_tokens"] = TOPIC_CHAPTER_LLM_MAX_OUTPUT_TOKENS

    response = litellm.completion(**completion_args)
    finish_reason = extract_litellm_finish_reason(response)
    usage = extract_litellm_usage(response)
    log.info(
        "%s LLM response metadata: finish_reason=%s usage=%s",
        phase_label,
        finish_reason,
        usage,
    )
    if finish_reason == "length":
        log.warning(
            "%s LLM response hit completion length limit; attempting "
            "parse/salvage before fallback",
            phase_label,
        )
    content = extract_litellm_content(response)
    expected_count = _extract_topic_chapter_count_from_text(content)
    parsed = _parse_topic_chapter_response(content)
    return parsed, content, finish_reason, expected_count


def _retry_incomplete_topic_chapter_plan(
    *,
    initial_plan: Sequence[tuple[int, str]],
    initial_expected_count: int | None,
    initial_finish_reason: str | None,
    blocks: list[dict[str, Any]],
    total_duration_ms: int,
    target_chapter_seconds: int,
    min_chapter_seconds: int,
    llm_model: str,
    llm_api_key: str | None,
    openai_base_url: str | None,
    openai_timeout_sec: int,
    logger_override: logging.Logger | None = None,
) -> list[tuple[int, str]]:
    log = logger_override or logger
    merged_plan = list(initial_plan)

    needs_retry = (
        initial_expected_count is not None and len(merged_plan) < initial_expected_count
    )
    if not needs_retry and initial_finish_reason == "length":
        # Even if chapter_count is missing/misreported, a length cutoff strongly
        # suggests the model may have more chapters to return.
        needs_retry = True
    if not needs_retry:
        return merged_plan

    retry_blocks, continuation_after_block_index = _build_topic_retry_blocks(
        blocks,
        existing_plan=merged_plan,
        overlap_blocks=TOPIC_CHAPTER_RETRY_OVERLAP_BLOCKS,
    )
    if not retry_blocks or continuation_after_block_index is None:
        log.info(
            "Topic chapter continuation retry skipped: no remaining blocks after "
            "recovered chapters"
        )
        return merged_plan

    log.info(
        "Retrying topic chapter generation for remaining blocks "
        "(existing_chapters=%d, expected_chapters=%s, retry_blocks=%d, "
        "continuation_after_block_index=%d, overlap_blocks=%d)",
        len(merged_plan),
        initial_expected_count,
        len(retry_blocks),
        continuation_after_block_index,
        TOPIC_CHAPTER_RETRY_OVERLAP_BLOCKS,
    )
    retry_prompt = _build_topic_chapter_generation_prompt(
        blocks=retry_blocks,
        total_duration_ms=total_duration_ms,
        target_chapter_seconds=target_chapter_seconds,
        min_chapter_seconds=min_chapter_seconds,
        continuation_after_block_index=continuation_after_block_index,
        existing_chapter_starts=[block_index for block_index, _ in merged_plan],
    )
    if not retry_prompt:
        log.warning(
            "Topic chapter continuation retry skipped: failed to build retry prompt"
        )
        return merged_plan

    log.info(
        "Topic chapter continuation prompt built (chars=%d, blocks=%d)",
        len(retry_prompt),
        len(retry_blocks),
    )
    retry_parsed, retry_content, retry_finish_reason, retry_expected = (
        _request_topic_chapter_plan(
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            openai_base_url=openai_base_url,
            prompt=retry_prompt,
            openai_timeout_sec=openai_timeout_sec,
            logger_override=log,
            phase_label="Topic chapter continuation",
        )
    )
    if not retry_parsed:
        log.warning(
            "Topic chapter continuation retry returned no parseable chapter plan; "
            "using recovered initial plan. response_snippet=%r finish_reason=%s",
            _truncate_for_log(retry_content),
            retry_finish_reason,
        )
        return merged_plan

    merged_plan = _merge_topic_plans_by_block_index(merged_plan, retry_parsed)
    log.info(
        "Merged topic chapter retry result (initial=%d, retry=%d, merged=%d)",
        len(initial_plan),
        len(retry_parsed),
        len(merged_plan),
    )
    if retry_expected is not None and len(retry_parsed) < retry_expected:
        log.warning(
            "Topic chapter continuation response appears incomplete after retry "
            "(expected=%d, parsed=%d)",
            retry_expected,
            len(retry_parsed),
        )
    return merged_plan


def _parse_topic_chapter_response(content: str) -> list[tuple[int, str]]:
    text = (content or "").strip()
    if not text:
        logger.warning(
            "LLM topic chapter response was empty; cannot parse topic chapter plan"
        )
        return []

    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    expected_count = _extract_topic_chapter_count_from_text(text)

    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        salvaged = _salvage_topic_chapter_response(text)
        if salvaged:
            if expected_count is not None and len(salvaged) < expected_count:
                logger.warning(
                    "Recovered partial topic chapter plan is incomplete: "
                    "expected %d chapters, recovered %d",
                    expected_count,
                    len(salvaged),
                )
            logger.warning(
                "Failed to parse full LLM topic chapter JSON response: %s. "
                "Recovered %d chapters from partial response.",
                exc,
                len(salvaged),
            )
            return salvaged
        logger.warning(
            "Failed to parse LLM topic chapter JSON response: %s snippet=%r",
            exc,
            _truncate_for_log(text),
        )
        return []

    items = data.get("chapters") if isinstance(data, dict) else None
    if not isinstance(items, list):
        logger.warning(
            "LLM topic chapter response missing 'chapters' list. keys=%s",
            sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
        )
        return []

    expected_count = _coerce_topic_chapter_count(
        data.get("chapter_count") if isinstance(data, dict) else None
    )
    out: list[tuple[int, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            block_index = int(item.get("block_index"))
        except Exception:  # noqa: BLE001
            continue
        title = str(item.get("title") or "").strip()
        out.append((block_index, title))

    if expected_count is None and isinstance(data, dict):
        logger.warning(
            "LLM topic chapter response missing valid 'chapter_count'; "
            "continuing with parsed chapters_count=%d",
            len(out),
        )
    elif expected_count is not None and expected_count != len(out):
        logger.warning(
            "LLM topic chapter response chapter_count mismatch: expected %d, "
            "parsed %d chapter entries",
            expected_count,
            len(out),
        )
    return out


def _coerce_topic_chapter_count(value: Any) -> int | None:
    try:
        count = int(value)
    except Exception:  # noqa: BLE001
        return None
    if count < 0:
        return None
    return count


def _extract_topic_chapter_count_from_text(content: str) -> int | None:
    text = (content or "").strip()
    if not text:
        return None
    match = re.search(r'"chapter_count"\s*:\s*(-?\d+)', text)
    if match is None:
        return None
    return _coerce_topic_chapter_count(match.group(1))


def _salvage_topic_chapter_response(content: str) -> list[tuple[int, str]]:
    """
    Best-effort recovery for truncated JSON responses.

    Extracts complete {block_index, title} pairs already emitted by the model even if
    the trailing JSON is cut off.
    """
    text = (content or "").strip()
    if not text:
        return []

    item_pattern = re.compile(
        r'"block_index"\s*:\s*(-?\d+)\s*,\s*"title"\s*:\s*"((?:[^"\\]|\\.)*)"'
    )

    out: list[tuple[int, str]] = []
    for match in item_pattern.finditer(text):
        try:
            block_index = int(match.group(1))
        except Exception:  # noqa: BLE001
            continue
        raw_title = match.group(2)
        try:
            title = json.loads(f'"{raw_title}"')
        except Exception:  # noqa: BLE001
            title = raw_title
        title = str(title).strip()
        if not title:
            continue
        out.append((block_index, title))

    deduped: list[tuple[int, str]] = []
    seen: set[int] = set()
    for block_index, title in out:
        if block_index in seen:
            continue
        seen.add(block_index)
        deduped.append((block_index, title))

    if deduped:
        logger.info(
            "Recovered %d partial topic chapters from truncated LLM response",
            len(deduped),
        )
    return deduped


def _build_topic_retry_blocks(
    blocks: Sequence[dict[str, Any]],
    *,
    existing_plan: Sequence[tuple[int, str]],
    overlap_blocks: int = 1,
) -> tuple[list[dict[str, Any]], int | None]:
    if not blocks or not existing_plan:
        return [], None

    max_existing_block_index = max(block_index for block_index, _ in existing_plan)
    ordered_blocks = sorted(blocks, key=lambda block: int(block["block_index"]))

    first_remaining_pos: int | None = None
    for idx, block in enumerate(ordered_blocks):
        if int(block["block_index"]) > max_existing_block_index:
            first_remaining_pos = idx
            break

    if first_remaining_pos is None:
        return [], max_existing_block_index

    retry_start_pos = max(0, first_remaining_pos - max(0, int(overlap_blocks)))
    return ordered_blocks[retry_start_pos:], max_existing_block_index


def _merge_topic_plans_by_block_index(
    primary_plan: Sequence[tuple[int, str]],
    secondary_plan: Sequence[tuple[int, str]],
) -> list[tuple[int, str]]:
    merged: list[tuple[int, str]] = []
    seen: set[int] = set()

    for block_index, title in list(primary_plan) + list(secondary_plan):
        if block_index in seen:
            continue
        seen.add(block_index)
        merged.append((int(block_index), str(title)))

    merged.sort(key=lambda item: item[0])
    return merged


def _chapters_from_topic_plan(
    plan: list[tuple[int, str]],
    *,
    blocks: list[dict[str, Any]],
    total_duration_ms: int,
    min_chapter_gap_ms: int,
) -> list[Chapter]:
    if not plan or not blocks:
        logger.warning(
            "Topic chapter plan validation failed: empty plan or no blocks "
            "(plan_items=%d, blocks=%d)",
            len(plan),
            len(blocks),
        )
        return []

    block_map = {int(b["block_index"]): b for b in blocks}
    valid_block_indexes = {int(b["block_index"]) for b in blocks}
    normalized = _normalize_topic_plan_entries(
        plan,
        valid_block_indexes=valid_block_indexes,
        block_map=block_map,
    )
    if not normalized:
        logger.warning(
            "Topic chapter plan validation failed: no valid block indexes in plan "
            "(plan_items=%d)",
            len(plan),
        )
        return []

    filtered = _filter_topic_plan_entries(
        normalized,
        block_map=block_map,
        min_chapter_gap_ms=min_chapter_gap_ms,
    )
    if not filtered:
        logger.warning(
            "Topic chapter plan validation failed: all chapters filtered out "
            "by minimum gap rule (min_gap_ms=%d)",
            min_chapter_gap_ms,
        )
        return []

    # If the model effectively returned one chapter for a long episode, treat
    # it as failure and fall back to the heuristic split.
    if len(filtered) == 1 and total_duration_ms >= 20 * 60 * 1000:
        logger.warning(
            "Topic chapter plan validation failed: model produced effectively one "
            "chapter for a long episode (duration_ms=%d)",
            total_duration_ms,
        )
        return []
    return _build_chapters_from_filtered_topic_plan(
        filtered,
        block_map=block_map,
        total_duration_ms=total_duration_ms,
    )


def _normalize_topic_plan_entries(
    plan: list[tuple[int, str]],
    *,
    valid_block_indexes: set[int],
    block_map: dict[int, dict[str, Any]],
) -> list[tuple[int, str]]:
    normalized: list[tuple[int, str]] = []
    seen: set[int] = set()

    for block_index, title in sorted(plan, key=lambda item: item[0]):
        if block_index not in valid_block_indexes or block_index in seen:
            continue
        seen.add(block_index)
        normalized.append((block_index, title))

    if not normalized:
        return []

    if normalized[0][0] != 0:
        first_text = str(block_map[0].get("text") or "")
        normalized.insert(0, (0, _chapter_title_from_text(first_text, 1)))

    return normalized


def _filter_topic_plan_entries(
    normalized: list[tuple[int, str]],
    *,
    block_map: dict[int, dict[str, Any]],
    min_chapter_gap_ms: int,
) -> list[tuple[int, str]]:
    filtered: list[tuple[int, str]] = []
    last_start_ms: int | None = None
    last_candidate_block_index = normalized[-1][0]

    for block_index, title in normalized:
        start_ms = int(block_map[block_index]["start_ms"])
        if filtered and last_start_ms is not None:
            gap_ms = start_ms - last_start_ms
            is_last_candidate = block_index == last_candidate_block_index
            if gap_ms < min_chapter_gap_ms and not is_last_candidate:
                continue
        filtered.append((block_index, title))
        last_start_ms = start_ms

    return filtered


def _build_chapters_from_filtered_topic_plan(
    filtered: list[tuple[int, str]],
    *,
    block_map: dict[int, dict[str, Any]],
    total_duration_ms: int,
) -> list[Chapter]:
    chapters: list[Chapter] = []

    for idx, (block_index, title) in enumerate(filtered):
        start_ms = int(block_map[block_index]["start_ms"])
        next_start_ms = total_duration_ms
        if idx + 1 < len(filtered):
            next_start_ms = int(block_map[filtered[idx + 1][0]]["start_ms"])

        title_value = title.strip() or _chapter_title_from_text(
            str(block_map[block_index].get("text") or ""),
            idx + 1,
        )
        chapters.append(
            Chapter(
                element_id=f"tgen{idx}",
                title=title_value,
                start_time_ms=max(0, start_ms),
                end_time_ms=max(start_ms, next_start_ms),
            )
        )

    return chapters


def _parse_refined_titles_response(content: str) -> dict[int, str]:
    text = (content or "").strip()
    if not text:
        return {}

    # Accept fenced JSON if the model wraps the response.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        return {}

    items = data.get("titles") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {}

    out: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
        except Exception:  # noqa: BLE001
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        out[idx] = title
    return out


def _format_timestamp(ms: int) -> str:
    total_seconds = max(0, ms // 1000)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _truncate_for_log(value: str, limit: int = 300) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _topic_chapter_count_cap_for_duration(duration_seconds: int) -> int:
    """Maximum chapter count allowed based on episode duration."""
    duration_seconds = max(1, int(duration_seconds))
    if duration_seconds < TOPIC_CHAPTER_SHORT_EPISODE_SECONDS:
        return TOPIC_CHAPTER_SHORT_EPISODE_CAP
    return math.ceil(duration_seconds / TOPIC_CHAPTER_CAP_WINDOW_SECONDS)
