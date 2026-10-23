"""Production quote-anchor classifier (spot-then-confirm).

Bag-of-words spotter windows (70s pad, bridged under 2 min, opening
isolate) → timestamp-free quote request on those regions only → in-order
fuzzy match → lexical_v2 → Identification rows + stored cuts.
AudioProcessor then applies ±2s silence snap (start-only earlier).
Fail-closed: never drop a reported ad (segment-edge, then chunk span).
The whole-transcript chunk walk is gone; ads with no spotter word are
not sent to the LLM.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

import litellm

from app.models import ModelCall, Post, TranscriptSegment
from app.writer.client import writer_client
from podcast_processor.ad_classifier import (
    ClassificationIncompleteError,
    InvalidModelOutputError,
)
from podcast_processor.ad_spotter import CandidateBreak, spot_candidates
from podcast_processor.boundary_snap import detect_silence_gaps, interpolate_word_times
from podcast_processor.quote_anchor import (
    QUOTE_ANCHOR_SOURCE,
    QuoteMatch,
    SegmentSpan,
    WordTiming,
    keep_ad,
    parse_quote_ads,
    quote_ads_json_is_usable,
    resolve_ads,
    word_index_range,
)
from podcast_processor.quote_anchor_prompt import (
    confirm_user_prompt,
    system_prompt_for,
)
from podcast_processor.quote_lexicon import lexical_cuts_from_matches
from podcast_processor.sponsor_lexicon import (  # noqa: F401
    PLATFORM_CTA_NAMES,
    PLATFORM_CTA_PHRASES,
    SELFPROMO_CUE_PHRASES,
    SELFPROMO_NAMES,
)
from podcast_processor.word_transcripts import (
    payload_is_aligned,
    reanchor_words_to_speech,
    transcribe_word_timestamps,
    word_cache_path_for_audio,
    words_from_payload,
)
from shared import defaults as DEFAULTS
from shared.config import Config, TestWhisperConfig

logger = logging.getLogger("global_logger")

QUOTE_PROMPT_VERSION = "v2"
SPOT_PAD_S = 50.0
SPOT_WIDE_PAD_S = float(DEFAULTS.SPOT_WIDE_PAD_SECONDS)
SPOT_BRIDGE_GAP_S = float(DEFAULTS.SPOT_BRIDGE_GAP_SECONDS)
SPOT_EDGE_SLACK_S = 5.0
SPOT_EXTEND_S = 50.0
SPOT_MAX_EXTENDS = 1
CompleteFn = Callable[[str, str], str]


def prompt_version_for(_config: Config | None = None) -> str:
    del _config
    return QUOTE_PROMPT_VERSION


def spot_lexicon_extras(
    config: Config,
    *,
    extra_phrases: tuple[str, ...] = (),
    extra_names: tuple[str, ...] = (),
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    del config
    return extra_phrases, extra_names


# Former ENABLE_SPOT_PLATFORM_CTA extras now live in CUE_PHRASES / SPONSOR_NAMES.
platform_cta_spot_extras = spot_lexicon_extras


def merge_spot_confirm_windows(
    candidates: Sequence[CandidateBreak],
    *,
    pad_s: float,
    ep_end: float,
    max_gap_s: float,
    isolate_opening: bool = False,
    opening_pad_s: float | None = None,
) -> list[tuple[float, float, tuple[CandidateBreak, ...]]]:
    """One LLM window per run of detections less than max_gap_s apart.

    Gap is between detection ends/starts (not padded edges). Default 120s.
    isolate_opening keeps the first cluster on opening_pad_s (default 50s)
    and never merges it into later detections, so a 70s/120s midroll
    bridge cannot grow the cold-open excerpt.

    Padding is clipped at neighboring clusters: a window never left-pads
    into the previous cluster or right-pads into the next one. Bridged
    detections stay one window, so this does not split a <2 min bridge.
    """
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda item: item.start)
    groups: list[list[CandidateBreak]] = [[ordered[0]]]
    for cand in ordered[1:]:
        if isolate_opening and len(groups) == 1 and len(groups[0]) == 1:
            groups.append([cand])
            continue
        prev = groups[-1][-1]
        if cand.start - prev.end < max_gap_s:
            groups[-1].append(cand)
        else:
            groups.append([cand])
    windows: list[tuple[float, float, tuple[CandidateBreak, ...]]] = []
    open_pad = SPOT_PAD_S if opening_pad_s is None else float(opening_pad_s)
    prev_cluster_end = 0.0
    for i, group in enumerate(groups):
        used_pad = open_pad if isolate_opening and i == 0 else pad_s
        cluster_end = max(item.end for item in group)
        start = max(0.0, min(item.start for item in group) - used_pad)
        if i > 0:
            # Do not pad backward into the previous cluster. A listen-CTA
            # split plus 70s left-pad would otherwise resend the earlier
            # promo and the model would stop at that first CTA again.
            start = max(start, prev_cluster_end)
        end = min(ep_end, cluster_end + used_pad)
        if i + 1 < len(groups):
            # Symmetric: do not right-pad into the next cluster, so Gemini
            # is not asked to quote past a listen-CTA split into the next
            # teaser. End is exclusive vs the next cluster start.
            next_start = min(item.start for item in groups[i + 1])
            end = min(end, next_start)
        if end <= start:
            prev_cluster_end = cluster_end
            continue
        windows.append((start, end, tuple(group)))
        prev_cluster_end = cluster_end
    return windows


def grouped_candidate(group: Sequence[CandidateBreak]) -> CandidateBreak:
    hits = tuple(hit for item in group for hit in item.hits)
    kinds = tuple(sorted({kind for item in group for kind in item.kinds}))
    return CandidateBreak(
        start=min(item.start for item in group),
        end=max(item.end for item in group),
        hits=hits,
        kinds=kinds,
        weight=sum(item.weight for item in group),
    )


def sent_window_word_range(
    words: list[WordTiming],
    *,
    sent_start: float,
    sent_end: float,
) -> tuple[int, int]:
    """Word search range for the transcript actually sent to the LLM."""
    return word_index_range(words, sent_start, sent_end)


def left_extend_adds_transcript(
    segments: Sequence[tuple[float, float]],
    *,
    chunk_start: float,
    window_start: float,
    window_end: float,
) -> bool:
    """True if a 50s backward extend would include an earlier segment."""
    new_start = max(0.0, window_start - SPOT_EXTEND_S)
    if new_start >= window_start - 1e-9:
        return False
    for seg_start, seg_end in segments:
        if seg_end > new_start and seg_start < window_end:
            return seg_start < chunk_start - 1e-6
    return False


def effective_spot_pad_s(
    _config: Config | None = None, *, override: float | None = None
) -> float:
    del _config
    return float(override) if override is not None else SPOT_WIDE_PAD_S


def effective_spot_bridge_gap_s(_config: Config | None = None) -> float:
    del _config
    return SPOT_BRIDGE_GAP_S


def union_confirm_matches(
    first: Sequence[QuoteMatch],
    second: Sequence[QuoteMatch],
) -> list[QuoteMatch]:
    """Keep every non-empty confirm span; never wipe a prior good result.

    Overlapping (or touching) spans are joined into one covering range so a
    later reply cannot clobber an earlier win. Non-overlapping extras from
    either confirm are kept.
    """
    kept: list[QuoteMatch] = []
    seen: set[tuple[float, float, str, str]] = set()
    for item in (*first, *second):
        if item.end <= item.start:
            continue
        key = (
            round(item.start, 3),
            round(item.end, 3),
            item.ad.start_quote,
            item.ad.end_quote,
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    kept.sort(key=lambda item: (item.start, item.end))
    merged: list[QuoteMatch] = []
    for item in kept:
        if merged and item.start <= merged[-1].end:
            prev = merged[-1]
            if item.end > prev.end:
                merged[-1] = QuoteMatch(
                    ad=prev.ad,
                    start=prev.start,
                    end=item.end,
                    method=prev.method if prev.score >= item.score else item.method,
                    score=max(prev.score, item.score),
                    dropped=False,
                    bound_start=prev.bound_start,
                    bound_end=item.bound_end
                    if item.end >= prev.end
                    else prev.bound_end,
                )
            continue
        merged.append(item)
    return merged


def effective_min_ad_segment_length_seconds(config: Config) -> float:
    return float(config.output.min_ad_segment_length_seconds)


def interpolate_words_from_segments(
    segments: list[TranscriptSegment],
) -> list[WordTiming]:
    words: list[WordTiming] = []
    for segment in segments:
        for span in interpolate_word_times(
            float(segment.start_time or 0.0),
            float(segment.end_time or segment.start_time or 0.0),
            str(segment.text or ""),
        ):
            words.append(WordTiming(word=span.word, start=span.start, end=span.end))
    return words


def segments_to_spans(segments: list[TranscriptSegment]) -> list[SegmentSpan]:
    return [
        SegmentSpan(
            start=float(segment.start_time or 0.0),
            end=float(segment.end_time or 0.0),
            text=str(segment.text or ""),
        )
        for segment in segments
    ]


class QuoteAnchorClassifier:
    """Identify ads by quotes, then cut with lexical_v2. Fail-closed."""

    def __init__(
        self,
        config: Config,
        logger: logging.Logger | None = None,
        db_session: Any | None = None,
        *,
        complete_fn: CompleteFn | None = None,
        word_cache_path: Path | None = None,
        llm_cache_dir: Path | None = None,
        llm_cache_dirs: Sequence[Path] | None = None,
        whisper_model: str = "base",
        require_llm_cache: bool = False,
        pull_dai_bed: bool = False,
        ngram_phrases: tuple[str, ...] = (),
        extra_phrases: tuple[str, ...] = (),
        extra_names: tuple[str, ...] = (),
        spot_pad_s: float | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("global_logger")
        self.db_session = db_session
        self.complete_fn = complete_fn
        self.word_cache_path = word_cache_path
        self.llm_cache_dir = llm_cache_dir
        extras = [Path(p) for p in (llm_cache_dirs or [])]
        if llm_cache_dir is not None and llm_cache_dir not in extras:
            extras.insert(0, Path(llm_cache_dir))
        self.llm_cache_dirs = extras
        self.whisper_model = whisper_model
        self.require_llm_cache = require_llm_cache
        self.pull_dai_bed = pull_dai_bed
        self.ngram_phrases = ngram_phrases
        self.extra_phrases = extra_phrases
        self.extra_names = extra_names
        self.spot_pad_s = spot_pad_s
        self.last_matches: list[QuoteMatch] = []
        self.last_cuts: list[tuple[float, float]] = []
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_llm_calls = 0
        self.last_extends = 0
        self.last_candidates: list[CandidateBreak] = []
        self.last_word_whisper_s = 0.0
        self.last_classify_s = 0.0
        self.silence_gaps_override: list[tuple[float, float]] | None = None

    def classify(
        self,
        *,
        transcript_segments: list[TranscriptSegment],
        post: Post,
        words: list[WordTiming] | None = None,
    ) -> list[tuple[float, float]]:
        started = time.time()
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_llm_calls = 0
        self.last_extends = 0
        self.last_candidates = []
        if not transcript_segments:
            self.last_matches = []
            self.last_cuts = []
            self._persist_cuts(post, [], [])
            self.last_classify_s = time.time() - started
            return []

        loaded = (
            words if words is not None else self.load_words(post, transcript_segments)
        )
        spans = segments_to_spans(transcript_segments)
        gaps = self._silence_gaps(post)
        loaded = reanchor_words_to_speech(loaded, spans, gaps)
        return self._classify_spot_then_confirm(
            transcript_segments=transcript_segments,
            post=post,
            loaded=loaded,
            spans=spans,
            gaps=gaps,
            started=started,
        )

    def _classify_spot_then_confirm(
        self,
        *,
        transcript_segments: list[TranscriptSegment],
        post: Post,
        loaded: list[WordTiming],
        spans: list[SegmentSpan],
        gaps: list[tuple[float, float]],
        started: float,
    ) -> list[tuple[float, float]]:
        extra_phrases, extra_names = spot_lexicon_extras(
            self.config,
            extra_phrases=self.extra_phrases,
            extra_names=self.extra_names,
        )
        candidates, stats = spot_candidates(
            loaded,
            extra_phrases=extra_phrases,
            extra_names=extra_names,
            ngram_phrases=self.ngram_phrases,
            drop_weak=True,
        )
        self.last_candidates = candidates
        ep_end = float(transcript_segments[-1].end_time or 0.0)
        matches: list[QuoteMatch] = []
        pad = effective_spot_pad_s(override=self.spot_pad_s)
        windows = merge_spot_confirm_windows(
            candidates,
            pad_s=pad,
            ep_end=ep_end,
            max_gap_s=effective_spot_bridge_gap_s(),
            isolate_opening=True,
        )
        for win_start, win_end, group in windows:
            cand = grouped_candidate(group)
            prior_end = max((item.end for item in matches), default=None)
            chunk_matches, extends = self._confirm_window(
                post=post,
                transcript_segments=transcript_segments,
                loaded=loaded,
                spans=spans,
                cand=cand,
                win_start=win_start,
                win_end=win_end,
                ep_end=ep_end,
                prior_end=prior_end,
            )
            self.last_extends += extends
            if any(item.dropped for item in chunk_matches):
                raise RuntimeError("quote-anchor dropped an ad; fail-closed violated")
            matches.extend(chunk_matches)

        cuts = lexical_cuts_from_matches(
            matches,
            loaded,
            gaps,
            pull_dai_bed=self.pull_dai_bed,
        )
        if len(cuts) < len(matches):
            used = {(round(a, 3), round(b, 3)) for a, b in cuts}
            for item in matches:
                key = (round(item.start, 3), round(item.end, 3))
                if item.end > item.start and key not in used:
                    cuts.append((item.start, item.end))
                    self.logger.warning(
                        "lexical dropped a quote span; restoring %.1f-%.1f",
                        item.start,
                        item.end,
                    )
        self.last_matches = matches
        self.last_cuts = cuts
        self._persist_cuts(post, cuts, matches)
        self.last_classify_s = time.time() - started
        self.logger.info(
            "spot-then-confirm post %s candidates=%s hits=%s calls=%s extends=%s quotes=%s cuts=%s",
            post.id,
            stats.n_candidates,
            stats.n_hits,
            self.last_llm_calls,
            self.last_extends,
            len(matches),
            len(cuts),
        )
        return cuts

    def _confirm_window(
        self,
        *,
        post: Post,
        transcript_segments: list[TranscriptSegment],
        loaded: list[WordTiming],
        spans: list[SegmentSpan],
        cand: CandidateBreak,
        win_start: float,
        win_end: float,
        ep_end: float,
        prior_end: float | None,
    ) -> tuple[list[QuoteMatch], int]:
        extends = 0
        matches: list[QuoteMatch] = []
        last_good: list[QuoteMatch] = []
        start = win_start
        end = win_end
        for _attempt in range(SPOT_MAX_EXTENDS + 1):
            chunk = [
                seg
                for seg in transcript_segments
                if float(seg.end_time or 0.0) > start
                and float(seg.start_time or 0.0) < end
            ]
            if not chunk:
                return [], extends
            user = confirm_user_prompt(
                title=str(post.title or ""),
                start_seconds=start,
                texts=[seg.text or "" for seg in chunk],
                prompt_version=prompt_version_for(self.config),
            )
            raw, model_call = self._complete_chunk(post=post, chunk=chunk, user=user)
            ads = [
                ad
                for ad in parse_quote_ads(raw)
                if keep_ad(ad, float(self.config.output.min_confidence))
            ]
            sent_start = float(chunk[0].start_time or 0.0)
            sent_end = float(chunk[-1].end_time or 0.0)
            w0, w1 = sent_window_word_range(
                loaded, sent_start=sent_start, sent_end=sent_end
            )
            # Fallback stays on the spotted cluster, not the padded window,
            # so an unmatched quote cannot cut ~100s of neighboring show.
            fallback_start = max(0.0, cand.start - 2.0)
            fallback_end = min(ep_end, max(cand.end + 2.0, fallback_start + 0.5))
            matches = resolve_ads(
                ads,
                loaded,
                spans,
                chunk_start=fallback_start,
                chunk_end=fallback_end,
                word_from=w0,
                word_to=w1,
                stop_before=prior_end,
                time_start=sent_start,
                time_end=sent_end,
            )
            if model_call is not None:
                self._write_identifications(chunk, matches, model_call)
            if matches:
                last_good = (
                    union_confirm_matches(last_good, matches) if last_good else matches
                )
            if not matches or extends >= SPOT_MAX_EXTENDS:
                break
            grew = False
            if start > 0.0 and any(
                item.start <= start + SPOT_EDGE_SLACK_S for item in matches
            ):
                # Keep npr_stack left-extends. Opening prefix word-bounds
                # must not skip ATP / Crime Junkie / Serial / Up First.
                start = max(0.0, start - SPOT_EXTEND_S)
                grew = True
            if end < ep_end - 1e-6 and any(
                item.end >= end - SPOT_EDGE_SLACK_S for item in matches
            ):
                end = min(ep_end, end + SPOT_EXTEND_S)
                grew = True
            if not grew:
                break
            extends += 1
        return last_good or matches, extends

    def load_words(
        self,
        post: Post,
        transcript_segments: list[TranscriptSegment],
    ) -> list[WordTiming]:
        if isinstance(self.config.whisper, TestWhisperConfig):
            return interpolate_words_from_segments(transcript_segments)
        audio = post.unprocessed_audio_path
        cache = self.word_cache_path
        if cache is None and audio:
            cache = word_cache_path_for_audio(audio)
        if cache is not None and cache.is_file():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                if payload_is_aligned(payload):
                    words = words_from_payload(payload)
                    if words:
                        return words
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                self.logger.warning("unreadable word cache %s", cache, exc_info=True)
        if audio and Path(str(audio)).is_file() and cache is not None:
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
            started = time.time()
            try:
                rows = [
                    (
                        float(seg.start_time or 0.0),
                        float(seg.end_time or 0.0),
                        str(seg.text or ""),
                    )
                    for seg in transcript_segments
                    if str(seg.text or "").strip()
                    and float(seg.end_time or 0.0) > float(seg.start_time or 0.0)
                ]
                words = transcribe_word_timestamps(
                    Path(str(audio)),
                    cache,
                    model_name=self.whisper_model,
                    segments=rows or None,
                )
                self.last_word_whisper_s = time.time() - started
                if words:
                    return words
            except Exception:
                self.logger.exception(
                    "segment word-align failed for post %s; interpolating",
                    post.id,
                )
                self.last_word_whisper_s = time.time() - started
        self.logger.warning(
            "interpolating word times from segments for post %s", post.id
        )
        return interpolate_words_from_segments(transcript_segments)

    def _silence_gaps(self, post: Post) -> list[tuple[float, float]]:
        if self.silence_gaps_override is not None:
            return list(self.silence_gaps_override)
        audio = post.unprocessed_audio_path
        if not audio or not Path(str(audio)).is_file():
            return []
        try:
            return [
                (gap.start, gap.end) for gap in detect_silence_gaps(Path(str(audio)))
            ]
        except Exception:  # noqa: BLE001
            self.logger.warning(
                "silencedetect failed for post %s", post.id, exc_info=True
            )
            return []

    def _complete_chunk(
        self,
        *,
        post: Post,
        chunk: list[TranscriptSegment],
        user: str,
    ) -> tuple[str, ModelCall | None]:
        system_prompt = system_prompt_for(prompt_version_for(self.config))
        model_call = self._upsert_model_call(
            post=post,
            first_seq_num=int(chunk[0].sequence_num),
            last_seq_num=int(chunk[-1].sequence_num),
            prompt=user,
        )
        self.last_llm_calls += 1
        if self.complete_fn is not None:
            try:
                content = self.complete_fn(system_prompt, user)
            except Exception as exc:  # noqa: BLE001
                self._fail_incomplete(model_call, exc)
            self._require_usable_quote_json(model_call, content)
            self._mark_model_call(model_call, content, status="success")
            return content, model_call
        cached = self._read_llm_cache(system_prompt, user)
        if cached is not None:
            self.last_input_tokens += int(cached.get("input_tokens") or 0)
            self.last_output_tokens += int(cached.get("output_tokens") or 0)
            content = str(cached.get("content") or '{"ads":[]}')
            self._mark_model_call(model_call, content, status="success")
            return content, model_call
        if self.require_llm_cache:
            raise RuntimeError("quote-anchor LLM cache miss; refusing live Gemini call")
        if isinstance(self.config.whisper, TestWhisperConfig):
            content = '{"ads":[]}'
            self._mark_model_call(model_call, content, status="success")
            return content, model_call
        try:
            content, pin, pout = self._call_llm(system_prompt, user)
        except Exception as exc:  # noqa: BLE001
            self._fail_incomplete(model_call, exc)
        self.last_input_tokens += pin
        self.last_output_tokens += pout
        self._write_llm_cache(system_prompt, user, content, pin, pout)
        self._mark_model_call(model_call, content, status="success")
        return content, model_call

    def _content_filter_error(self, error: Exception) -> bool:
        return isinstance(error, RuntimeError) and "content_filter" in str(error)

    def _fail_incomplete(
        self, model_call: ModelCall | None, error: Exception
    ) -> NoReturn:
        message = str(error)
        self._mark_model_call(
            model_call,
            "",
            status="failed_permanent",
            error_message=message,
        )
        raise ClassificationIncompleteError(
            f"Ad classification incomplete for quote-anchor window: {message}"
        ) from error

    def _require_usable_quote_json(
        self, model_call: ModelCall | None, content: str
    ) -> None:
        if quote_ads_json_is_usable(content):
            return
        self._fail_incomplete(
            model_call,
            InvalidModelOutputError("LLM response is not valid quote-ad JSON"),
        )

    def _usable_llm_content(self, *, finish_reason: Any, content: str | None) -> str:
        if finish_reason == "length":
            raise InvalidModelOutputError(
                "LLM response truncated at the output token limit "
                "(finish_reason=length)"
            )
        if finish_reason == "content_filter":
            raise RuntimeError("LLM response withheld (finish_reason=content_filter)")
        if content is None or not str(content).strip():
            raise InvalidModelOutputError("LLM response has no content")
        if not quote_ads_json_is_usable(content):
            raise InvalidModelOutputError("LLM response is not valid quote-ad JSON")
        return content

    def _call_llm(self, system_prompt: str, user: str) -> tuple[str, int, int]:
        last_error: Exception | None = None
        retries = int(getattr(self.config, "llm_max_retry_attempts", 5) or 5)
        for attempt in range(retries):
            try:
                response = litellm.completion(
                    model=self.config.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user},
                    ],
                    timeout=int(getattr(self.config, "openai_timeout", 300) or 300),
                    response_format={"type": "json_object"},
                    max_tokens=512,
                    reasoning_effort="low",
                    api_key=self.config.llm_api_key,
                )
                choice = response.choices[0]
                content = self._usable_llm_content(
                    finish_reason=getattr(choice, "finish_reason", None),
                    content=getattr(choice.message, "content", None),
                )
                usage = getattr(response, "usage", None)
                pin = int(getattr(usage, "prompt_tokens", 0) or 0)
                pout = int(getattr(usage, "completion_tokens", 0) or 0)
                return content, pin, pout
            except Exception as exc:
                last_error = exc
                text = str(exc).lower()
                retryable = isinstance(exc, InvalidModelOutputError) or (
                    "503" in text
                    or "unavailable" in text
                    or "429" in text
                    or "rate limit" in text
                    or "internal" in text
                    or "name resolution" in text
                    or "apiconnectionerror" in text
                    or "connecterror" in text
                    or "connect" in text
                )
                if self._content_filter_error(exc):
                    retryable = False
                if not retryable or attempt >= retries - 1:
                    raise
                delay = min(32.0, 4.0 * (2**attempt))
                self.logger.warning(
                    "quote-anchor Gemini retry %s after %.0fs: %s",
                    attempt + 1,
                    delay,
                    type(exc).__name__,
                )
                time.sleep(delay)
        raise last_error or RuntimeError("quote-anchor LLM call failed")

    def _cache_key(self, system_prompt: str, user: str) -> str:
        return hashlib.sha1(f"{system_prompt}\n---\n{user}".encode()).hexdigest()

    def _read_llm_cache(self, system_prompt: str, user: str) -> dict[str, Any] | None:
        key = f"{self._cache_key(system_prompt, user)}.json"
        dirs: list[Path] = []
        for path in self.llm_cache_dirs:
            if path not in dirs:
                dirs.append(path)
        if self.llm_cache_dir is not None and self.llm_cache_dir not in dirs:
            dirs.insert(0, self.llm_cache_dir)
        for cache_dir in dirs:
            path = cache_dir / key
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
        return None

    def _write_llm_cache(
        self,
        system_prompt: str,
        user: str,
        content: str,
        pin: int,
        pout: int,
    ) -> None:
        if self.llm_cache_dir is None:
            return
        self.llm_cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.llm_cache_dir / f"{self._cache_key(system_prompt, user)}.json"
        path.write_text(
            json.dumps(
                {
                    "content": content,
                    "input_tokens": pin,
                    "output_tokens": pout,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _upsert_model_call(
        self,
        *,
        post: Post,
        first_seq_num: int,
        last_seq_num: int,
        prompt: str,
    ) -> ModelCall | None:
        if post.id is None:
            return None
        result = writer_client.action(
            "upsert_model_call",
            {
                "post_id": post.id,
                "model_name": self.config.llm_model,
                "first_segment_sequence_num": first_seq_num,
                "last_segment_sequence_num": last_seq_num,
                "prompt": prompt,
            },
            wait=True,
        )
        if not result or not result.success:
            self.logger.error(
                "quote-anchor failed to upsert ModelCall: %s",
                getattr(result, "error", None),
            )
            return None
        model_call_id = (result.data or {}).get("model_call_id")
        session = self.db_session
        if session is None or model_call_id is None:
            return None
        return session.get(ModelCall, int(model_call_id))

    def _mark_model_call(
        self,
        model_call: ModelCall | None,
        content: str,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        if model_call is None or model_call.id is None:
            return
        writer_client.update(
            "ModelCall",
            model_call.id,
            {
                "response": content,
                "status": status,
                "error_message": error_message,
                "retry_attempts": 1,
            },
            wait=True,
        )
        model_call.response = content
        model_call.status = status
        model_call.error_message = error_message

    def _write_identifications(
        self,
        chunk: list[TranscriptSegment],
        matches: list[QuoteMatch],
        model_call: ModelCall,
    ) -> None:
        if not matches or model_call.id is None:
            return
        to_insert: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in matches:
            confidence = max(float(item.ad.confidence), float(item.score))
            for segment in chunk:
                if segment.id is None or segment.id in seen:
                    continue
                if min(item.end, float(segment.end_time)) <= max(
                    item.start, float(segment.start_time)
                ):
                    continue
                seen.add(segment.id)
                to_insert.append(
                    {
                        "transcript_segment_id": segment.id,
                        "model_call_id": model_call.id,
                        "label": "ad",
                        "confidence": confidence,
                    }
                )
        if not to_insert:
            return
        res = writer_client.action(
            "insert_identifications",
            {"identifications": to_insert},
            wait=True,
        )
        if not res or not res.success:
            raise RuntimeError(
                getattr(res, "error", "Failed to insert quote-anchor identifications")
            )

    def _persist_cuts(
        self,
        post: Post,
        cuts: list[tuple[float, float]],
        matches: list[QuoteMatch],
    ) -> None:
        if post.id is None:
            return
        payload: list[dict[str, Any]] = [
            {
                "source": QUOTE_ANCHOR_SOURCE,
                "empty": not cuts,
                "n_quotes": len(matches),
                "n_word": sum(1 for item in matches if item.method == "word"),
                "n_segment_fallback": sum(
                    1 for item in matches if item.method == "segment_fallback"
                ),
                "n_chunk_fallback": sum(
                    1 for item in matches if item.method == "chunk_fallback"
                ),
                "orig_start": 0.0,
                "orig_end": 0.0,
                "refined_start": 0.0,
                "refined_end": 0.0,
            }
        ]
        for cut, item in _zip_cuts_to_matches(cuts, matches):
            payload.append(
                {
                    "source": QUOTE_ANCHOR_SOURCE,
                    "orig_start": float(item.start if item is not None else cut[0]),
                    "orig_end": float(item.end if item is not None else cut[1]),
                    "refined_start": float(cut[0]),
                    "refined_end": float(cut[1]),
                    "method": item.method if item is not None else "lexical",
                    "score": float(item.score) if item is not None else 0.0,
                    "start_quote": item.ad.start_quote if item is not None else "",
                    "end_quote": item.ad.end_quote if item is not None else "",
                    "empty": False,
                }
            )
        res = writer_client.update(
            "Post",
            post.id,
            {
                "refined_ad_boundaries": payload,
                "refined_ad_boundaries_updated_at": datetime.now(UTC).replace(
                    tzinfo=None
                ),
            },
            wait=True,
        )
        if not res or not res.success:
            raise RuntimeError(
                getattr(res, "error", "Failed to persist quote-anchor cuts")
            )
        post.refined_ad_boundaries = payload


def _zip_cuts_to_matches(
    cuts: list[tuple[float, float]],
    matches: list[QuoteMatch],
) -> list[tuple[tuple[float, float], QuoteMatch | None]]:
    remaining = list(matches)
    paired: list[tuple[tuple[float, float], QuoteMatch | None]] = []
    for cut in cuts:
        best: QuoteMatch | None = None
        best_overlap = 0.0
        for item in remaining:
            overlap = max(0.0, min(cut[1], item.end) - max(cut[0], item.start))
            if overlap > best_overlap:
                best_overlap = overlap
                best = item
        if best is not None and best_overlap > 0.0:
            remaining.remove(best)
            paired.append((cut, best))
        else:
            paired.append((cut, None))
    return paired
