"""$0 candidate-ad spotter over word-level transcripts.

Keyword/cue + sponsor-name matching (Whisper-tolerant), nearby clustering,
and optional cross-episode repeated n-grams. Does not call an LLM.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from podcast_processor.quote_anchor import WordTiming, normalize_tokens
from podcast_processor.sponsor_lexicon import (
    CUE_PHRASES,
    SPONSOR_NAMES,
    URL_TLDS,
    fold_alnum,
    name_folds,
    phrase_tokens,
)

CLUSTER_GAP_S = 40.0
MAX_CLUSTER_S = 150.0
MAX_CANDIDATES = 20
# Packed same-sentence listen-CTAs stay in one cluster; a later promo after
# a listen-CTA is a new unit. Generic cues only (not "npr app").
LISTEN_CTA_CUES = frozenset(
    {
        "wherever you get your podcasts",
        "wherever you listen",
    }
)
LISTEN_CTA_SPLIT_GAP_S = 3.0
STRONG_KINDS = frozenset({"cue", "url", "promo", "ngram"})
NGRAM_N = 6
NGRAM_MIN_EPISODES = 2
# Dotted hosts only. Bare `ca` stays out of URL_TLDS (Canada / ca.).
URL_RE = re.compile(
    r"\b[a-z0-9][a-z0-9\-]*\.(?:com|org|net|io|fm|ca)\b",
    re.I,
)
PROMO_RE = re.compile(r"\b(?:promo\s+code|use\s+code|code\s+[a-z0-9]{3,})\b", re.I)
SLASH_RE = re.compile(r"\bslash\b|/", re.I)


@dataclass(frozen=True)
class SpotHit:
    start: float
    end: float
    kind: str
    cue: str
    weight: float = 1.0
    word_from: int = 0
    word_to: int = 0


@dataclass(frozen=True)
class CandidateBreak:
    start: float
    end: float
    hits: tuple[SpotHit, ...]
    kinds: tuple[str, ...]
    weight: float

    @property
    def mid(self) -> float:
        return 0.5 * (self.start + self.end)


@dataclass
class SpotterStats:
    n_hits: int = 0
    n_candidates: int = 0
    n_cues: int = 0
    n_sponsors: int = 0
    n_urls: int = 0
    n_ngrams: int = 0
    notes: list[str] = field(default_factory=list)


def _token_stream(words: list[WordTiming]) -> list[tuple[int, str]]:
    stream: list[tuple[int, str]] = []
    for idx, word in enumerate(words):
        for token in normalize_tokens(word.word):
            stream.append((idx, token))
    return stream


def _letter_runs(stream: list[tuple[int, str]]) -> list[tuple[int, int, str]]:
    """Collapse runs of single-letter Whisper spell-outs (D-O-P-P-E-L)."""
    runs: list[tuple[int, int, str]] = []
    i = 0
    while i < len(stream):
        if len(stream[i][1]) != 1:
            i += 1
            continue
        j = i
        letters: list[str] = []
        while j < len(stream) and len(stream[j][1]) == 1:
            letters.append(stream[j][1])
            j += 1
        if len(letters) >= 4:
            runs.append((stream[i][0], stream[j - 1][0], "".join(letters)))
        i = j
    return runs


def _window_ok(quote: list[str], window: list[str]) -> bool:
    if not quote:
        return False
    if window[: len(quote)] == quote:
        return True
    extra = 1 if len(quote) >= 3 else 0
    if len(window) > len(quote) + extra:
        window = window[: len(quote) + extra]
    # Insertions only (Whisper extras). Do not allow substitutions —
    # "back to the interview" must not match "back to the show".
    k = 0
    for token in window:
        if k < len(quote) and token == quote[k]:
            k += 1
    return k == len(quote)


def _hits_for_phrase(
    words: list[WordTiming],
    stream: list[tuple[int, str]],
    phrase: str,
    *,
    kind: str,
    weight: float,
) -> list[SpotHit]:
    needle = phrase_tokens(phrase)
    if not needle:
        return []
    hits: list[SpotHit] = []
    n = len(needle)
    max_win = n + (1 if n >= 3 else 0)
    first = needle[0]
    for i, (_idx, tok) in enumerate(stream):
        if tok != first:
            continue
        window_toks: list[str] = []
        last_idx = stream[i][0]
        for j in range(i, min(len(stream), i + max_win)):
            window_toks.append(stream[j][1])
            last_idx = stream[j][0]
            if len(window_toks) < n:
                continue
            if _window_ok(needle, window_toks):
                w0 = stream[i][0]
                hits.append(
                    SpotHit(
                        start=words[w0].start,
                        end=words[last_idx].end,
                        kind=kind,
                        cue=phrase,
                        weight=weight,
                        word_from=w0,
                        word_to=last_idx + 1,
                    )
                )
                break
    return hits


def _dedupe_hits(hits: list[SpotHit]) -> list[SpotHit]:
    ordered = sorted(hits, key=lambda h: (h.start, -h.weight, h.end))
    kept: list[SpotHit] = []
    seen: set[tuple[str, int, int]] = set()
    for hit in ordered:
        key = (hit.kind, round(hit.start), round(hit.end))
        if key in seen:
            continue
        seen.add(key)
        kept.append(hit)
    return kept


def spot_hits(
    words: list[WordTiming],
    *,
    extra_phrases: tuple[str, ...] = (),
    extra_names: tuple[str, ...] = (),
) -> list[SpotHit]:
    if not words:
        return []
    stream = _token_stream(words)
    hits: list[SpotHit] = []
    for phrase in (*CUE_PHRASES, *extra_phrases):
        hits.extend(_hits_for_phrase(words, stream, phrase, kind="cue", weight=1.2))
    names = (*SPONSOR_NAMES, *extra_names)
    for name in names:
        if " " in name or "." in name:
            hits.extend(
                _hits_for_phrase(words, stream, name, kind="sponsor", weight=1.6)
            )
    folds = set(name_folds())
    folds.update(fold_alnum(n) for n in extra_names if len(fold_alnum(n)) >= 4)
    # Sliding folded windows of 1-4 words.
    for i, word in enumerate(words):
        for width in (1, 2, 3, 4):
            if i + width > len(words):
                break
            blob = fold_alnum(" ".join(w.word for w in words[i : i + width]))
            if len(blob) < 4:
                continue
            if blob in folds:
                hits.append(
                    SpotHit(
                        start=word.start,
                        end=words[i + width - 1].end,
                        kind="sponsor",
                        cue=blob,
                        weight=1.6,
                        word_from=i,
                        word_to=i + width,
                    )
                )
    for w0, w1, spelled in _letter_runs(stream):
        if spelled in folds:
            hits.append(
                SpotHit(
                    start=words[w0].start,
                    end=words[w1].end,
                    kind="sponsor",
                    cue=spelled,
                    weight=1.8,
                    word_from=w0,
                    word_to=w1 + 1,
                )
            )
    for i, word in enumerate(words):
        raw = word.word
        if "." not in raw and "/" not in raw and "code" not in raw.lower():
            window = words[i : i + 4]
            text = " ".join(w.word for w in window)
            if "code" not in text.lower() and "." not in text:
                # cheap skip; tld/slash still handled below
                pass
            else:
                if URL_RE.search(text):
                    hits.append(
                        SpotHit(
                            start=word.start,
                            end=window[-1].end,
                            kind="url",
                            cue="url",
                            weight=1.7,
                            word_from=i,
                            word_to=i + len(window),
                        )
                    )
                if PROMO_RE.search(text):
                    hits.append(
                        SpotHit(
                            start=word.start,
                            end=window[-1].end,
                            kind="promo",
                            cue="promo",
                            weight=1.5,
                            word_from=i,
                            word_to=i + len(window),
                        )
                    )
        else:
            window = words[i : i + 8]
            text = " ".join(w.word for w in window)
            if URL_RE.search(text):
                hits.append(
                    SpotHit(
                        start=word.start,
                        end=window[-1].end,
                        kind="url",
                        cue="url",
                        weight=1.7,
                        word_from=i,
                        word_to=i + len(window),
                    )
                )
            if PROMO_RE.search(text):
                hits.append(
                    SpotHit(
                        start=word.start,
                        end=window[-1].end,
                        kind="promo",
                        cue="promo",
                        weight=1.5,
                        word_from=i,
                        word_to=i + len(window),
                    )
                )
        parts = normalize_tokens(word.word)
        if any(part in URL_TLDS for part in parts) and i > 0:
            hits.append(
                SpotHit(
                    start=words[i - 1].start,
                    end=word.end,
                    kind="url",
                    cue="tld",
                    weight=1.4,
                    word_from=i - 1,
                    word_to=i + 1,
                )
            )
        if SLASH_RE.search(word.word) or parts == ["slash"]:
            hits.append(
                SpotHit(
                    start=word.start,
                    end=word.end,
                    kind="url",
                    cue="slash",
                    weight=1.3,
                    word_from=i,
                    word_to=i + 1,
                )
            )
    return _dedupe_hits(hits)


def _is_listen_cta_hit(hit: SpotHit) -> bool:
    return hit.kind == "cue" and hit.cue in LISTEN_CTA_CUES


def cluster_hits(
    hits: list[SpotHit],
    *,
    gap_s: float = CLUSTER_GAP_S,
    max_span_s: float = MAX_CLUSTER_S,
    max_candidates: int = MAX_CANDIDATES,
) -> list[CandidateBreak]:
    if not hits:
        return []
    ordered = sorted(hits, key=lambda h: h.start)
    groups: list[list[SpotHit]] = [[ordered[0]]]
    for hit in ordered[1:]:
        cur = groups[-1]
        span0 = cur[0].start
        split_after_listen_cta = any(_is_listen_cta_hit(item) for item in cur) and (
            hit.start - cur[-1].end > LISTEN_CTA_SPLIT_GAP_S
        )
        if (
            not split_after_listen_cta
            and hit.start - cur[-1].end <= gap_s
            and hit.end - span0 <= max_span_s
        ):
            cur.append(hit)
        else:
            groups.append([hit])
    candidates: list[CandidateBreak] = []
    for group in groups:
        kinds = tuple(sorted({h.kind for h in group}))
        weight = sum(h.weight for h in group)
        candidates.append(
            CandidateBreak(
                start=min(h.start for h in group),
                end=max(h.end for h in group),
                hits=tuple(group),
                kinds=kinds,
                weight=weight,
            )
        )
    candidates.sort(key=lambda c: -c.weight)
    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]
    candidates.sort(key=lambda c: c.start)
    return candidates


def ngram_key(tokens: list[str]) -> str:
    return " ".join(tokens)


def repeated_ngrams(
    episodes: dict[str, list[WordTiming]],
    *,
    n: int = NGRAM_N,
    min_episodes: int = NGRAM_MIN_EPISODES,
) -> tuple[str, ...]:
    """Phrases that repeat across episodes (same show or global catalog)."""
    per_ep: dict[str, set[str]] = {}
    for ep_id, words in episodes.items():
        toks = [t for _, t in _token_stream(words)]
        keys: set[str] = set()
        for i in range(0, max(0, len(toks) - n + 1)):
            chunk = toks[i : i + n]
            if sum(1 for t in chunk if len(t) >= 3) < max(3, n - 2):
                continue
            keys.add(ngram_key(chunk))
        per_ep[ep_id] = keys
    counts: Counter[str] = Counter()
    for keys in per_ep.values():
        counts.update(keys)
    return tuple(key for key, n_ep in counts.items() if n_ep >= min_episodes)


def ngram_hits(words: list[WordTiming], phrases: tuple[str, ...]) -> list[SpotHit]:
    if not phrases:
        return []
    stream = _token_stream(words)
    hits: list[SpotHit] = []
    for phrase in phrases:
        hits.extend(_hits_for_phrase(words, stream, phrase, kind="ngram", weight=1.1))
    return hits


def is_weak_candidate(cand: CandidateBreak) -> bool:
    """Lone company name with no cue/url/ngram corroboration."""
    kinds = set(cand.kinds)
    if kinds & STRONG_KINDS:
        return False
    return kinds <= {"sponsor"}


def drop_weak_candidates(
    candidates: list[CandidateBreak],
) -> list[CandidateBreak]:
    return [cand for cand in candidates if not is_weak_candidate(cand)]


def spot_candidates(
    words: list[WordTiming],
    *,
    extra_phrases: tuple[str, ...] = (),
    extra_names: tuple[str, ...] = (),
    ngram_phrases: tuple[str, ...] = (),
    gap_s: float = CLUSTER_GAP_S,
    max_span_s: float = MAX_CLUSTER_S,
    max_candidates: int = MAX_CANDIDATES,
    drop_weak: bool = False,
) -> tuple[list[CandidateBreak], SpotterStats]:
    hits = spot_hits(words, extra_phrases=extra_phrases, extra_names=extra_names)
    if ngram_phrases:
        hits.extend(ngram_hits(words, ngram_phrases))
        hits = _dedupe_hits(hits)
    candidates = cluster_hits(
        hits, gap_s=gap_s, max_span_s=max_span_s, max_candidates=max_candidates
    )
    if drop_weak:
        candidates = drop_weak_candidates(candidates)
    stats = SpotterStats(
        n_hits=len(hits),
        n_candidates=len(candidates),
        n_cues=sum(1 for h in hits if h.kind == "cue"),
        n_sponsors=sum(1 for h in hits if h.kind == "sponsor"),
        n_urls=sum(1 for h in hits if h.kind in {"url", "promo"}),
        n_ngrams=sum(1 for h in hits if h.kind == "ngram"),
    )
    return candidates, stats


def gold_misses(
    gold_spans: list[tuple[float, float, str, str]],
    candidates: list[CandidateBreak],
    *,
    min_overlap_s: float = 1.0,
) -> list[dict[str, object]]:
    """Gold ads with no overlapping candidate (unrecoverable in this design)."""
    missed: list[dict[str, object]] = []
    for start, end, show_id, text in gold_spans:
        hit = False
        for cand in candidates:
            overlap = min(end, cand.end) - max(start, cand.start)
            if overlap >= min_overlap_s:
                hit = True
                break
        if not hit:
            missed.append(
                {
                    "show_id": show_id,
                    "start": start,
                    "end": end,
                    "text": text,
                }
            )
    return missed


def group_words_by_show(
    catalog: dict[str, list[WordTiming]],
) -> dict[str, dict[str, list[WordTiming]]]:
    grouped: dict[str, dict[str, list[WordTiming]]] = defaultdict(dict)
    for key, words in catalog.items():
        show = key.split(":", 1)[0]
        grouped[show][key] = words
    return grouped
