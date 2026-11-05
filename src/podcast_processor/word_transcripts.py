"""Word timings for quote-anchor: forced-align segment Whisper text.

openai-whisper `word_timestamps=True` rewinds `seek` to the last DTW word
inside each 30s window (`whisper/transcribe.py`). On full episodes that
skips DAI/music beds that segment decode already transcribed (Indicator
Wise+donate, Up First 865-887). Alignment does not re-decode and cannot
drop segment speech.
"""

from __future__ import annotations

import json
import logging
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

from podcast_processor.boundary_snap import interpolate_word_times
from podcast_processor.quote_anchor import WordTiming

logger = logging.getLogger(__name__)

ALIGNED_BACKEND = "segment_align"


def word_cache_path_for_audio(audio_path: str | Path) -> Path:
    path = Path(audio_path)
    return path.with_name(path.name + ".words.json")


ALIGN_WINDOW_S = 28.0
ALIGN_PAD_S = 0.25
MAX_ALIGN_AUDIO_S = 29.9
MIN_SPEECH_SILENCE_S = 0.8
STRETCH_MEAN_WORD_S = 0.7
PACK_WORD_S = 0.35
MIN_LEAD_BED_S = 2.0
# Re-decode inter-segment holes. Full-episode Whisper can skip a 30s window
# when DAI/music-bed speech follows a bumper (Indicator 1431 Wise 57-84).
# Clip re-decode recovers it; music-only beds fail logprob and stay empty.
HOLE_FILL_MIN_S = 8.0
HOLE_FILL_MAX_S = 60.0
HOLE_FILL_LOGPROB_MIN = -1.0
HOLE_FILL_NO_SPEECH_MAX = 0.6
HOLE_FILL_MAX_SEC_PER_WORD = 2.0
SegmentRow = tuple[float, float, str]


def payload_is_aligned(payload: dict[str, Any] | None) -> bool:
    return bool(payload) and str(payload.get("backend") or "") == ALIGNED_BACKEND


def words_from_payload(payload: dict[str, Any]) -> list[WordTiming]:
    words: list[WordTiming] = []
    for row in payload.get("words") or []:
        token = str(row.get("word") or "").strip()
        if not token:
            continue
        words.append(
            WordTiming(
                word=token,
                start=float(row["start"]),
                end=float(row["end"]),
            )
        )
    if words:
        return words
    for seg in payload.get("segments") or []:
        text = str(seg.get("text") or "")
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)
        for span in interpolate_word_times(start, end, text):
            words.append(WordTiming(word=span.word, start=span.start, end=span.end))
    return words


def save_word_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def payload_from_whisper_result(
    result: dict[str, Any],
    *,
    model_name: str,
    audio_path: Path | str,
) -> dict[str, Any]:
    """Legacy decoder-path payload. Do not use for matching; prefer segment_align."""
    words_out: list[dict[str, Any]] = []
    segments_out: list[dict[str, Any]] = []
    for seg in result.get("segments") or []:
        seg_words = []
        for item in seg.get("words") or []:
            token = str(item.get("word") or "").strip()
            if not token:
                continue
            row = {
                "word": token,
                "start": float(
                    item.get("start")
                    if item.get("start") is not None
                    else seg.get("start") or 0.0
                ),
                "end": float(
                    item.get("end")
                    if item.get("end") is not None
                    else seg.get("end") or 0.0
                ),
            }
            seg_words.append(row)
            words_out.append(row)
        segments_out.append(
            {
                "start": float(seg.get("start") or 0.0),
                "end": float(seg.get("end") or 0.0),
                "text": str(seg.get("text") or ""),
                "words": seg_words,
            }
        )
        if not seg_words:
            for span in interpolate_word_times(
                float(seg.get("start") or 0.0),
                float(seg.get("end") or 0.0),
                str(seg.get("text") or ""),
            ):
                words_out.append(
                    {"word": span.word, "start": span.start, "end": span.end}
                )
    return {
        "model": model_name,
        "word_timestamps": True,
        "audio_path": str(audio_path),
        "words": words_out,
        "segments": segments_out,
    }


def segments_from_payload(payload: dict[str, Any]) -> list[tuple[float, float, str]]:
    rows: list[tuple[float, float, str]] = []
    for seg in payload.get("segments") or []:
        rows.append(
            (
                float(seg.get("start") or 0.0),
                float(seg.get("end") or 0.0),
                str(seg.get("text") or ""),
            )
        )
    return rows


def fill_whisper_segment_holes(
    audio_path: Path | str,
    segments: list[dict[str, Any]],
    model: Any,
    *,
    language: str = "en",
    min_hole_s: float = HOLE_FILL_MIN_S,
    max_hole_s: float = HOLE_FILL_MAX_S,
    load_audio: Any | None = None,
    sample_rate: int | None = None,
) -> list[dict[str, Any]]:
    """Re-transcribe long gaps between kept segments; keep speech, drop beds.

    openai-whisper skips a whole 30s window when `no_speech_prob` is high on
    that window of a *long* file. The same audio as a short clip transcribes.
    Re-decode holes and keep rows that pass Whisper's own logprob / no-speech
    gates so music beds (Up First 865-887) are not hallucinated into text.
    """
    segs = sorted(segments, key=lambda row: float(row.get("start") or 0.0))
    if len(segs) < 2 or model is None:
        return segs
    loader = load_audio
    rate = sample_rate
    if loader is None or rate is None:
        from whisper.audio import SAMPLE_RATE
        from whisper.audio import load_audio as whisper_load_audio

        loader = loader or whisper_load_audio
        rate = int(rate or SAMPLE_RATE)

    audio = None
    added: list[dict[str, Any]] = []
    for left, right in pairwise(segs):
        t0 = float(left.get("end") or 0.0)
        t1 = float(right.get("start") or 0.0)
        hole = t1 - t0
        if hole < min_hole_s or hole > max_hole_s:
            continue
        if audio is None:
            audio = loader(str(audio_path))
        a0 = max(0, int(t0 * rate))
        a1 = min(int(audio.shape[0]), int(t1 * rate))
        clip = audio[a0:a1]
        if clip.shape[0] < int(0.4 * rate):
            continue
        result = model.transcribe(
            clip,
            fp16=False,
            language=language,
            word_timestamps=False,
        )
        for row in result.get("segments") or []:
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            if float(row.get("avg_logprob") or -99.0) <= HOLE_FILL_LOGPROB_MIN:
                continue
            if float(row.get("no_speech_prob") or 1.0) > HOLE_FILL_NO_SPEECH_MAX:
                continue
            start = t0 + float(row.get("start") or 0.0)
            end = t0 + float(row.get("end") or start)
            start = max(t0, min(t1, start))
            end = max(start, min(t1, end))
            if end - start < 0.15:
                continue
            n_words = len(text.split())
            if n_words < 1:
                continue
            if (end - start) / n_words > HOLE_FILL_MAX_SEC_PER_WORD:
                continue
            filled = dict(row)
            filled["start"] = start
            filled["end"] = end
            filled["text"] = text
            added.append(filled)
            logger.info("hole-fill kept %.1f-%.1f %r", start, end, text[:80])
    if not added:
        return segs
    merged = segs + added
    merged.sort(key=lambda row: float(row.get("start") or 0.0))
    return merged


def segment_rows_from_transcript(raw: Any) -> list[SegmentRow]:
    rows = raw.get("segments") if isinstance(raw, dict) else raw
    out: list[SegmentRow] = []
    for seg in rows or []:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg["start"])
        end = float(seg["end"])
        if end <= start:
            continue
        out.append((start, end, text))
    return out


def group_segment_rows(
    rows: list[SegmentRow], *, max_span_s: float = ALIGN_WINDOW_S
) -> list[list[SegmentRow]]:
    """Pack consecutive segments into windows Whisper can align (≤30s mel)."""
    groups: list[list[SegmentRow]] = []
    current: list[SegmentRow] = []
    origin = 0.0
    for row in rows:
        start, end, _text = row
        if end - start > max_span_s:
            if current:
                groups.append(current)
                current = []
            groups.append([row])
            continue
        if not current:
            current = [row]
            origin = start
            continue
        if end - origin <= max_span_s:
            current.append(row)
            continue
        groups.append(current)
        current = [row]
        origin = start
    if current:
        groups.append(current)
    return groups


def _interpolate_rows(rows: list[SegmentRow]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for start, end, text in rows:
        words.extend(lexicon_words_for_segment(start, end, text, dtw_words=None))
    return words


def lexicon_words_for_segment(
    start: float,
    end: float,
    text: str,
    dtw_words: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Keep every segment token. Use DTW times only when the word count matches."""
    expected = interpolate_word_times(start, end, text)
    if not expected:
        return []
    linear = [
        {"word": span.word, "start": span.start, "end": span.end} for span in expected
    ]
    if not dtw_words:
        return linear
    sane: list[dict[str, Any]] = []
    for row in dtw_words:
        a = float(row["start"])
        b = float(row["end"])
        if b < a:
            a, b = b, a
        if b - a > 2.5 or b < start - 0.25 or a > end + 0.25:
            continue
        sane.append({"word": str(row.get("word") or "").strip(), "start": a, "end": b})
    if len(sane) == len(expected):
        out: list[dict[str, Any]] = []
        prev = start
        for span, row in zip(expected, sane, strict=True):
            a = max(prev, float(row["start"]))
            b = float(row["end"])
            if b <= a:
                b = a + max(0.02, span.end - span.start)
            out.append({"word": span.word, "start": a, "end": b})
            prev = b
        return out
    # Count mismatch: keep lexicon labels but time them on the DTW speech
    # span, not the full Whisper segment (which often includes a music bed).
    t0 = max(start, min(float(row["start"]) for row in sane))
    t1 = min(end, max(float(row["end"]) for row in sane))
    if t1 - t0 < 0.05:
        return linear
    return [
        {"word": span.word, "start": span.start, "end": span.end}
        for span in interpolate_word_times(t0, t1, text)
    ]


def lock_words_to_segment_lexicon(
    dtw_words: list[dict[str, Any]],
    rows: list[SegmentRow],
) -> list[dict[str, Any]]:
    """Re-label DTW timings with segment tokens so quote matching cannot drop speech."""
    assigned: list[list[dict[str, Any]]] = [[] for _ in rows]
    for row in dtw_words:
        a = float(row["start"])
        b = float(row["end"])
        best_i = -1
        best_ov = 0.0
        for i, (start, end, _text) in enumerate(rows):
            ov = min(b, end) - max(a, start)
            if ov > best_ov:
                best_ov = ov
                best_i = i
        if best_i >= 0 and best_ov > 0:
            assigned[best_i].append(row)
    locked: list[dict[str, Any]] = []
    for (start, end, text), bucket in zip(rows, assigned, strict=True):
        locked.extend(lexicon_words_for_segment(start, end, text, dtw_words=bucket))
    locked.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    return locked


def speech_intervals(
    start: float,
    end: float,
    gaps: list[tuple[float, float]],
    *,
    min_sil: float = MIN_SPEECH_SILENCE_S,
) -> list[tuple[float, float]]:
    """[start, end] minus silences of at least min_sil."""
    sils: list[tuple[float, float]] = []
    for g0, g1 in gaps:
        a = max(start, float(g0))
        b = min(end, float(g1))
        if b - a >= min_sil:
            sils.append((a, b))
    sils.sort()
    intervals: list[tuple[float, float]] = []
    cursor = float(start)
    for a, b in sils:
        if a > cursor:
            intervals.append((cursor, a))
        cursor = max(cursor, b)
    if end > cursor:
        intervals.append((cursor, float(end)))
    return intervals


def _map_onto_intervals(u: float, intervals: list[tuple[float, float]]) -> float:
    acc = 0.0
    for a, b in intervals:
        dur = b - a
        if acc + dur >= u:
            return a + (u - acc)
        acc += dur
    return intervals[-1][1]


def _place_tokens_on_intervals(
    tokens: list[str], intervals: list[tuple[float, float]]
) -> list[WordTiming]:
    total = sum(b - a for a, b in intervals)
    if not tokens or total <= 0:
        return []
    n = len(tokens)
    out: list[WordTiming] = []
    for i, token in enumerate(tokens):
        t0 = _map_onto_intervals(total * i / n, intervals)
        t1 = _map_onto_intervals(total * (i + 1) / n, intervals)
        if t1 <= t0:
            t1 = t0 + 0.02
        out.append(WordTiming(word=token, start=t0, end=t1))
    last = out[-1]
    out[-1] = WordTiming(word=last.word, start=last.start, end=intervals[-1][1])
    return out


def _seg_start_end(seg: Any) -> tuple[float, float]:
    if isinstance(seg, tuple):
        return float(seg[0]), float(seg[1])
    return float(seg.start), float(seg.end)


def reanchor_words_to_speech(
    words: list[WordTiming],
    segments: list[Any],
    gaps: list[tuple[float, float]] | None = None,
) -> list[WordTiming]:
    """Pull linearly stretched words off music beds and restore pause holes.

    Whisper segment times often include a DAI/music bed. When DTW count
    mismatches we interpolated across that bed (Threat Locker 465-475,
    Planet Money 1215 pause). $0 post-process: pack leading-bed stretches
    at the segment tail, and redistribute off ≥0.8s silences.
    """
    if not words or not segments:
        return words
    gap_rows = [(float(a), float(b)) for a, b in (gaps or [])]
    bounds = [_seg_start_end(seg) for seg in segments]
    assigned: list[list[WordTiming]] = [[] for _ in segments]
    leftover: list[WordTiming] = []
    j = 0
    n_seg = len(bounds)
    for word in words:
        while j < n_seg and bounds[j][1] <= word.start:
            j += 1
        best_i = -1
        best_ov = 0.0
        for k in range(max(0, j - 1), min(n_seg, j + 3)):
            start, end = bounds[k]
            ov = min(word.end, end) - max(word.start, start)
            if ov > best_ov:
                best_ov = ov
                best_i = k
        if best_i >= 0 and best_ov > 0:
            assigned[best_i].append(word)
        else:
            leftover.append(word)

    out: list[WordTiming] = list(leftover)
    prev_end: float | None = None
    for i, seg in enumerate(segments):
        bucket = assigned[i]
        if not bucket:
            continue
        start, end = _seg_start_end(seg)
        clipped: list[WordTiming] = []
        for word in bucket:
            clipped_word = _clip_word_off_silence(word, gap_rows)
            if clipped_word is not None:
                clipped.append(clipped_word)
        bucket = clipped
        if not bucket:
            continue
        intervals = speech_intervals(start, end, gap_rows)
        span = bucket[-1].end - bucket[0].start
        mean = span / float(len(bucket))
        packed = PACK_WORD_S * len(bucket)
        fully_spanned = (
            abs(bucket[0].start - start) < 0.45 and abs(bucket[-1].end - end) < 0.45
        )
        leading_bed = (
            fully_spanned
            and mean >= 1.0
            and (end - start) >= packed + 4.0
            and prev_end is not None
            and (start - prev_end) >= MIN_LEAD_BED_S
        )
        trailing_pause = (
            not leading_bed
            and intervals
            and abs(bucket[0].start - intervals[0][0]) < 0.5
            and (intervals[0][1] - intervals[0][0]) >= packed * 0.5
            and (end - intervals[0][1]) >= MIN_SPEECH_SILENCE_S
        )
        if leading_bed:
            t1 = end
            t0 = max(start, t1 - packed)
            if intervals:
                last_a, last_b = intervals[-1]
                pack = min(last_b - last_a, packed)
                if pack >= 0.15:
                    t1 = last_b
                    t0 = max(last_a, t1 - pack)
            bucket = _place_tokens_on_intervals(
                [word.word for word in bucket], [(t0, t1)]
            )
        elif trailing_pause:
            bucket = _place_tokens_on_intervals(
                [word.word for word in bucket], [intervals[0]]
            )
        out.extend(bucket)
        if bucket:
            prev_end = bucket[-1].end
    return _order_word_blocks(out)


def _order_word_blocks(words: list[WordTiming]) -> list[WordTiming]:
    """Keep overlapping duplicate alignments as whole sentences.

    A global time-sort interleaved Indicator 1433 ("The President's…" over
    "Three years after October 7th") so consecutive quote-match failed.
    Split only on a backward time jump, then order those blocks.
    """
    if not words:
        return words
    blocks: list[list[WordTiming]] = []
    current = [words[0]]
    for word in words[1:]:
        prev = current[-1]
        if word.start + 0.05 >= prev.start:
            current.append(word)
        else:
            blocks.append(current)
            current = [word]
    blocks.append(current)
    blocks.sort(key=lambda block: (block[0].start, block[0].end))
    return [word for block in blocks for word in block]


def _clip_word_off_silence(
    word: WordTiming, gaps: list[tuple[float, float]]
) -> WordTiming | None:
    """Shrink a word so it does not cover a ≥0.8s silence; drop if nothing left."""
    start, end = word.start, word.end
    for a, b in gaps:
        if (b - a) < MIN_SPEECH_SILENCE_S:
            continue
        overlap = min(end, b) - max(start, a)
        if overlap <= 0.12:
            continue
        before = max(0.0, min(end, a) - start)
        after = max(0.0, end - max(start, b))
        if after >= before:
            start = max(start, b)
            end = max(end, start + 0.05)
        else:
            end = min(end, a)
            if end <= start:
                return None
    if end - start < 0.02:
        return None
    if start == word.start and end == word.end:
        return word
    return WordTiming(word=word.word, start=start, end=end)


def align_words_to_segments(
    audio_path: Path,
    rows: list[SegmentRow],
    *,
    model: Any,
    language: str = "en",
) -> tuple[list[dict[str, Any]], float]:
    """DTW-align known segment text onto audio. One decoder pass per ~28s group."""
    from whisper.audio import (
        N_FRAMES,
        SAMPLE_RATE,
        load_audio,
        log_mel_spectrogram,
        pad_or_trim,
    )
    from whisper.timing import add_word_timestamps
    from whisper.tokenizer import get_tokenizer

    started = time.time()
    if not rows:
        return [], 0.0
    audio = load_audio(str(audio_path))
    tokenizer = get_tokenizer(
        model.is_multilingual, language=language, task="transcribe"
    )
    n_mels = int(getattr(model.dims, "n_mels", 80))
    words: list[dict[str, Any]] = []
    for group in group_segment_rows(rows):
        try:
            words.extend(
                _align_group(
                    audio,
                    group,
                    model=model,
                    tokenizer=tokenizer,
                    n_mels=n_mels,
                    sample_rate=SAMPLE_RATE,
                    n_frames=N_FRAMES,
                    pad_or_trim=pad_or_trim,
                    log_mel_spectrogram=log_mel_spectrogram,
                    add_word_timestamps=add_word_timestamps,
                )
            )
        except Exception:
            logger.exception(
                "segment align failed %.1f-%.1f; interpolating group",
                group[0][0],
                group[-1][1],
            )
            words.extend(_interpolate_rows(group))
    return words, time.time() - started


def _align_group(
    audio: Any,
    group: list[SegmentRow],
    *,
    model: Any,
    tokenizer: Any,
    n_mels: int,
    sample_rate: int,
    n_frames: int,
    pad_or_trim: Any,
    log_mel_spectrogram: Any,
    add_word_timestamps: Any,
) -> list[dict[str, Any]]:
    t0 = max(0.0, float(group[0][0]) - ALIGN_PAD_S)
    t1 = float(group[-1][1]) + ALIGN_PAD_S
    if t1 - t0 > MAX_ALIGN_AUDIO_S:
        t1 = t0 + MAX_ALIGN_AUDIO_S
    a0 = int(t0 * sample_rate)
    a1 = min(int(audio.shape[0]), int(t1 * sample_rate))
    clip = audio[a0:a1]
    if clip.shape[0] < int(0.05 * sample_rate):
        return _interpolate_rows(group)
    mel = log_mel_spectrogram(clip, n_mels=n_mels)
    num_frames = int(mel.shape[-1])
    mel = pad_or_trim(mel, n_frames).to(model.device)
    segs: list[dict[str, Any]] = []
    sources: list[SegmentRow] = []
    skipped: list[SegmentRow] = []
    for row in group:
        start, end, text = row
        tokens = [tok for tok in tokenizer.encode(text) if tok < tokenizer.eot]
        if not tokens:
            skipped.append(row)
            continue
        rel_start = max(0.0, start - t0)
        rel_end = min(t1 - t0, max(rel_start + 0.02, end - t0))
        segs.append(
            {
                "seek": 0,
                "start": rel_start,
                "end": rel_end,
                "text": text,
                "tokens": tokens,
            }
        )
        sources.append(row)
    if not segs:
        return _interpolate_rows(group)
    add_word_timestamps(
        segments=segs,
        model=model,
        tokenizer=tokenizer,
        mel=mel,
        num_frames=min(num_frames, n_frames),
        last_speech_timestamp=0.0,
    )
    aligned: list[dict[str, Any]] = []
    for seg, row in zip(segs, sources, strict=True):
        start, end, text = row
        seg_words = []
        for item in seg.get("words") or []:
            token = str(item.get("word") or "").strip()
            if not token:
                continue
            seg_words.append(
                {
                    "word": token,
                    "start": t0 + float(item["start"]),
                    "end": t0 + float(item["end"]),
                }
            )
        aligned.extend(
            lexicon_words_for_segment(start, end, text, dtw_words=seg_words or None)
        )
    if skipped:
        aligned.extend(_interpolate_rows(skipped))
    aligned.sort(key=lambda item: (float(item["start"]), float(item["end"])))
    return aligned


def payload_from_aligned_words(
    words: list[dict[str, Any]],
    rows: list[SegmentRow],
    *,
    model_name: str,
    audio_path: Path | str,
    align_s: float,
) -> dict[str, Any]:
    return {
        "model": model_name,
        "backend": ALIGNED_BACKEND,
        "word_timestamps": False,
        "audio_path": str(audio_path),
        "align_s": round(align_s, 3),
        "words": words,
        "segments": [
            {"start": start, "end": end, "text": text} for start, end, text in rows
        ],
    }


def load_word_cache(
    path: Path, *, aligned_only: bool = True
) -> list[WordTiming] | None:
    payload = load_word_payload(path)
    if payload is None:
        return None
    if aligned_only and not payload_is_aligned(payload):
        return None
    words = words_from_payload(payload)
    return words or None


def load_word_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def transcribe_word_timestamps(
    audio_path: Path,
    cache_path: Path,
    *,
    model_name: str = "base",
    language: str = "en",
    model: Any | None = None,
    segments: list[SegmentRow] | None = None,
) -> list[WordTiming]:
    cached = load_word_cache(cache_path, aligned_only=True)
    if cached:
        return cached
    import whisper

    loaded = model if model is not None else whisper.load_model(name=model_name)
    rows = list(segments or [])
    if not rows:
        logger.info("segment whisper then align %s model=%s", audio_path, model_name)
        result = loaded.transcribe(
            str(audio_path),
            fp16=False,
            language=language,
            word_timestamps=False,
        )
        result["segments"] = fill_whisper_segment_holes(
            audio_path,
            list(result.get("segments") or []),
            loaded,
            language=language,
        )
        rows = segment_rows_from_transcript(result)
    logger.info("aligning %s segments on %s", len(rows), audio_path)
    words, align_s = align_words_to_segments(
        audio_path, rows, model=loaded, language=language
    )
    payload = payload_from_aligned_words(
        words,
        rows,
        model_name=model_name,
        audio_path=audio_path,
        align_s=align_s,
    )
    save_word_cache(cache_path, payload)
    logger.info("aligned %s words in %.1fs -> %s", len(words), align_s, cache_path)
    return words_from_payload(payload)
