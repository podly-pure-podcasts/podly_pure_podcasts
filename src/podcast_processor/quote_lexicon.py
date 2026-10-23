"""$0 acoustic refine of quote-matched cuts using word timings and pauses.

Phrase-based catch/removal rules were deleted (2026-10-21): sister-teaser-skip,
sister-stack-tail, platform-cta cutter, opening-only Cadillac word-bounds,
bridge-trim-30, and lead-in/CTA/sister forward-trim. The LLM decides ad
boundaries; this module only snaps to word timings, t=0 prerolls, long
wordless holes, and silence. Show IDs stay in TUNE_NOTES only.
"""

from __future__ import annotations

from dataclasses import dataclass

from podcast_processor.quote_anchor import QuoteMatch, WordTiming, word_index_range

BACKFILL_MAX_S = 4.0
MIN_LONG_HOLE_S = 12.0
MAX_HOLE_PULL_S = 25.0
MIN_END_HOLE_S = 3.0
SHORT_END_HOLE_S = 5.0
MAX_END_HOLE_S = 15.0
PREROLL_SNAP_S = 3.0
UNION_START_SLACK_S = 25.0


@dataclass(frozen=True)
class LexicalTuneNote:
    rule: str
    motivated_by: str
    class_hint: str


TUNE_NOTES = (
    LexicalTuneNote(
        "pull_start_across_long_prequote_hole",
        "npr_up_first 868 (21s post-roll hole after closer)",
        "f_label_off",
    ),
    LexicalTuneNote(
        "pull_start_across_dai_bed_8_to_12s",
        "holdout npr_indicator 422 (9s wordless DAI bed before Wait Wait; now-seen; default off — no original-10 lift)",
        "a_missed_leadin",
    ),
    LexicalTuneNote(
        "extend_end_to_silence_in_word_gap",
        "darknet_diaries 53-61 long bed (silence start); planet_money 21-24 short CTA music (silence end)",
        "b_missed_outro",
    ),
    LexicalTuneNote(
        "snap_preroll_start_to_zero",
        "darknet_diaries opening 0-2s before first word",
        "a_missed_leadin",
    ),
)


def refine_quote_span(
    words: list[WordTiming],
    start: float,
    end: float,
    *,
    gaps: list[tuple[float, float]] | None = None,
    max_forward_s: float = 20.0,
    min_hole_s: float = MIN_LONG_HOLE_S,
    max_hole_s: float = MAX_HOLE_PULL_S,
    pull_dai_bed: bool = False,
    resume_trim: bool = False,
    backfill_leadin: bool = False,
    closer_tail: bool = False,
    bridge_trim_30: bool = False,
    sister_stack_tail: bool = False,
    sister_teaser_skip: bool = False,
) -> tuple[float, float]:
    """Snap a quote span to word timings, t=0, holes, and silence.

    Keyword leftovers (resume_trim, sister_*, bridge_trim_30, …) are ignored.
    They remain in the signature so older experiment callers do not crash.
    """
    del (
        max_forward_s,
        resume_trim,
        backfill_leadin,
        closer_tail,
        bridge_trim_30,
        sister_stack_tail,
        sister_teaser_skip,
    )
    if not words or end <= start:
        return start, end
    lo, hi = word_index_range(words, start, end)
    if hi <= lo:
        return start, end

    start_t = words[lo].start
    if lo > 0:
        prev = words[lo - 1]
        hole = words[lo].start - prev.end
        long_ok = min_hole_s <= hole <= max_hole_s
        dai_bed = pull_dai_bed and 8.0 <= hole < min_hole_s and hole <= max_hole_s
        if long_ok or dai_bed:
            start_t = prev.end

    if start < PREROLL_SNAP_S:
        start_t = 0.0

    end_t = words[hi - 1].end
    if hi < len(words):
        next_gap = words[hi].start - words[hi - 1].end
        if MIN_END_HOLE_S <= next_gap <= MAX_END_HOLE_S:
            t0 = words[hi - 1].end
            t1 = words[hi].start
            silence_hits = [
                (float(g0), float(g1))
                for g0, g1 in (gaps or [])
                if t0 - 0.2 <= float(g0) <= t1 + 0.05 and (g1 - g0) >= 0.4
            ]
            if silence_hits:
                g0, g1 = min(silence_hits, key=lambda item: item[0])
                end_t = g1 if next_gap < SHORT_END_HOLE_S else g0

    if end_t <= start_t:
        return start, end
    return start_t, end_t


def union_v1_v2_cuts(
    v2: list[tuple[float, float]],
    v1: list[tuple[float, float]],
    *,
    slack_s: float = UNION_START_SLACK_S,
) -> list[tuple[float, float]]:
    """$0 merge of cached prompt-v1 and prompt-v2 quote spans."""
    out: list[tuple[float, float]] = []
    for start, end in v2:
        overlapping = [(a, b) for a, b in v1 if min(end, b) > max(start, a)]
        new_start, new_end = start, end
        if overlapping:
            v1_start = min(a for a, _ in overlapping)
            if start < v1_start <= start + slack_s:
                new_start = v1_start
            v1_end = max(b for _, b in overlapping)
            new_end = max(new_end, v1_end)
        if new_end > new_start:
            out.append((new_start, new_end))
    for start, end in v1:
        if end <= start:
            continue
        if not any(min(end, b) > max(start, a) for a, b in v2):
            out.append((start, end))
    return out


def lexical_cuts_from_matches(
    matches: list[QuoteMatch],
    words: list[WordTiming],
    gaps: list[tuple[float, float]] | None = None,
    *,
    asymmetric_end: bool = False,
    pull_dai_bed: bool = False,
    resume_trim: bool = False,
    backfill_leadin: bool = False,
    closer_tail: bool = False,
    bridge_trim_30: bool = False,
    sister_stack_tail: bool = False,
    sister_teaser_skip: bool = False,
) -> list[tuple[float, float]]:
    del resume_trim, backfill_leadin, closer_tail, bridge_trim_30
    del sister_stack_tail, sister_teaser_skip
    cuts: list[tuple[float, float]] = []
    for item in matches:
        if item.end <= item.start:
            continue
        start, end = refine_quote_span(
            words,
            item.start,
            item.end,
            gaps=gaps,
            pull_dai_bed=pull_dai_bed,
        )
        if asymmetric_end and item.bound_end is not None and item.bound_end > end:
            end = float(item.bound_end)
        if end > start:
            cuts.append((start, end))
    return cuts
