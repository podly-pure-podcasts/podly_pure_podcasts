"""$0 cut-edge refinement: silence/low-energy snap + interpolated word extents.

Does not call an LLM. Intended for eval-first, then production if scorecard
gates pass. Scout confirm stays off.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SnapPrefer = Literal["nearest", "inward", "earlier_start"]

logger = logging.getLogger(__name__)

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

DEFAULT_RADIUS_SECONDS = 2.0
DEFAULT_MIN_SILENCE_SECONDS = 0.25
DEFAULT_NOISE_DB = -35.0
DEFAULT_MIN_CUT_SECONDS = 1.0


@dataclass(frozen=True)
class SilenceGap:
    start: float
    end: float


@dataclass(frozen=True)
class WordSpan:
    word: str
    start: float
    end: float


_WORD_RE = re.compile(r"\S+")
_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def interpolate_word_times(start: float, end: float, text: str) -> list[WordSpan]:
    """Linear word timestamps inside a Whisper segment (no word-level ASR)."""
    tokens = _WORD_RE.findall(text or "")
    if not tokens:
        return []
    duration = max(0.0, float(end) - float(start))
    step = duration / float(len(tokens)) if duration > 0 else 0.0
    spans: list[WordSpan] = []
    cursor = float(start)
    for token in tokens:
        token_end = cursor + step
        spans.append(WordSpan(word=token, start=cursor, end=token_end))
        cursor = token_end
    if spans:
        spans[-1] = WordSpan(word=spans[-1].word, start=spans[-1].start, end=float(end))
    return spans


def trim_cut_to_word_extents(
    cut: tuple[float, float],
    segments: list[tuple[float, float, str]],
) -> tuple[float, float]:
    """Trim a cut to the first/last interpolated ad-segment words it covers.

    Segment-aligned cuts are unchanged. Mid-segment cuts snap to word edges.
    """
    start, end = float(cut[0]), float(cut[1])
    overlapping = [
        (s0, s1, text) for s0, s1, text in segments if min(s1, end) > max(s0, start)
    ]
    if not overlapping:
        return start, end
    first_words = interpolate_word_times(*overlapping[0])
    last_words = interpolate_word_times(*overlapping[-1])
    if first_words:
        start = max(start, first_words[0].start)
    if last_words:
        end = min(end, last_words[-1].end)
    if end <= start:
        return float(cut[0]), float(cut[1])
    return start, end


def parse_silencedetect(text: str, *, time_offset: float = 0.0) -> list[SilenceGap]:
    starts = [float(m.group(1)) + time_offset for m in _SILENCE_START_RE.finditer(text)]
    ends = [float(m.group(1)) + time_offset for m in _SILENCE_END_RE.finditer(text)]
    gaps: list[SilenceGap] = []
    for idx, start in enumerate(starts):
        end = ends[idx] if idx < len(ends) else start
        end = max(end, start)
        gaps.append(SilenceGap(start=start, end=end))
    if len(ends) > len(starts):
        for end in ends[len(starts) :]:
            gaps.append(SilenceGap(start=end, end=end))
    return gaps


def snap_time_to_silence(
    t: float,
    gaps: list[SilenceGap],
    radius: float,
    *,
    kind: Literal["start", "end"],
    prefer: SnapPrefer = "nearest",
) -> float:
    """Snap a cut start to the nearest silence_end, or an end to silence_start."""
    candidates: list[float] = []
    for gap in gaps:
        snap = gap.end if kind == "start" else gap.start
        if abs(snap - t) > radius:
            continue
        if prefer == "inward":
            if kind == "start" and snap < t:
                continue
            if kind == "end" and snap > t:
                continue
        elif prefer == "earlier_start":
            if kind == "start" and snap > t:
                continue
        candidates.append(snap)
    if not candidates:
        return t
    return min(candidates, key=lambda value: (abs(value - t), abs(value)))


def snap_cuts_to_silence(
    cuts: list[tuple[float, float]],
    gaps: list[SilenceGap],
    *,
    radius: float = DEFAULT_RADIUS_SECONDS,
    min_length: float = DEFAULT_MIN_CUT_SECONDS,
    prefer: SnapPrefer = "nearest",
) -> list[tuple[float, float]]:
    refined: list[tuple[float, float]] = []
    for start, end in cuts:
        new_start = snap_time_to_silence(
            start, gaps, radius, kind="start", prefer=prefer
        )
        new_end = snap_time_to_silence(end, gaps, radius, kind="end", prefer=prefer)
        if new_end - new_start < min_length:
            refined.append((start, end))
            continue
        refined.append((new_start, new_end))
    return _merge_cuts(refined)


def _merge_cuts(cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not cuts:
        return []
    ordered = sorted((float(a), float(b)) for a, b in cuts if float(b) > float(a))
    if not ordered:
        return []
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def detect_silence_gaps(
    audio_path: Path,
    *,
    noise_db: float = DEFAULT_NOISE_DB,
    min_silence: float = DEFAULT_MIN_SILENCE_SECONDS,
) -> list[SilenceGap]:
    """Run silencedetect on a whole file (cache this; do not loop per edge)."""
    if not shutil.which("ffmpeg") or not audio_path.is_file():
        return []
    cmd = [
        FFMPEG,
        "-hide_banner",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f",
        "null",
        "-",
    ]
    try:
        completed = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=240
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("silencedetect failed for %s: %s", audio_path, exc)
        return []
    text = (completed.stderr or "") + (completed.stdout or "")
    return parse_silencedetect(text)


def detect_silence_gaps_near(
    audio_path: Path,
    centers: list[float],
    *,
    radius: float = DEFAULT_RADIUS_SECONDS,
    noise_db: float = DEFAULT_NOISE_DB,
    min_silence: float = DEFAULT_MIN_SILENCE_SECONDS,
) -> list[SilenceGap]:
    if not shutil.which("ffmpeg") or not audio_path.is_file():
        return []
    gaps: list[SilenceGap] = []
    pad = 0.5
    for center in centers:
        extract_start = max(0.0, float(center) - radius - pad)
        duration = (radius + pad) * 2.0
        cmd = [
            FFMPEG,
            "-hide_banner",
            "-ss",
            f"{extract_start:.3f}",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d={min_silence}",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = subprocess.run(
                cmd, check=False, capture_output=True, text=True, timeout=60
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("silencedetect failed near %.2fs: %s", center, exc)
            continue
        text = (completed.stderr or "") + (completed.stdout or "")
        gaps.extend(parse_silencedetect(text, time_offset=extract_start))
    return gaps


def refine_cuts(
    cuts: list[tuple[float, float]],
    *,
    audio_path: Path | None = None,
    segments: list[tuple[float, float, str]] | None = None,
    radius: float = DEFAULT_RADIUS_SECONDS,
    min_length: float = DEFAULT_MIN_CUT_SECONDS,
    prefer: SnapPrefer = "nearest",
    gaps: list[SilenceGap] | None = None,
) -> list[tuple[float, float]]:
    """Eval/production hook: word extents, then silence snap if audio exists."""
    word_trimmed: list[tuple[float, float]] = []
    for cut in cuts:
        if segments:
            word_trimmed.append(trim_cut_to_word_extents(cut, segments))
        else:
            word_trimmed.append((float(cut[0]), float(cut[1])))
    resolved_gaps = gaps
    if resolved_gaps is None and audio_path is not None:
        resolved_gaps = detect_silence_gaps(audio_path)
    if not resolved_gaps:
        return _merge_cuts(word_trimmed)
    return snap_cuts_to_silence(
        word_trimmed,
        resolved_gaps,
        radius=radius,
        min_length=min_length,
        prefer=prefer,
    )
