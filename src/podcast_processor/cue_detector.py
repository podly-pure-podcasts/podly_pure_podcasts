import re
from re import Pattern

# Production analyze() keys. Extra scout keys are appended only when
# include_scout_extras=True so AdClassifier neighbor expansion is unchanged.
CORE_ANALYZE_KEYS: tuple[str, ...] = (
    "url",
    "promo",
    "phone",
    "cta",
    "transition",
    "self_promo",
)
STRONG_CUE_KEYS: tuple[str, ...] = ("url", "promo", "phone", "cta")
SCOUT_EXTRA_KEYS: tuple[str, ...] = ("sponsor", "ad_break")

# Weights used by score(). Strong cues match AdClassifier neighbor expansion.
DEFAULT_SIGNAL_WEIGHTS: dict[str, float] = {
    "url": 1.0,
    "promo": 1.0,
    "phone": 1.0,
    "cta": 0.8,
    "transition": 0.5,
    "self_promo": 0.4,
    "sponsor": 1.0,
    "ad_break": 0.7,
}


class CueDetector:
    def __init__(self, include_scout_extras: bool = False) -> None:
        self.include_scout_extras = include_scout_extras
        self.url_pattern: Pattern[str] = re.compile(
            r"\b([a-z0-9\-\.]+\.(?:com|net|org|io))\b", re.I
        )
        self.promo_pattern: Pattern[str] = re.compile(
            r"\b(code|promo|save|discount)\s+\w+\b", re.I
        )
        self.phone_pattern: Pattern[str] = re.compile(
            r"\b(?:\+?1[ -]?)?\d{3}[ -]?\d{3}[ -]?\d{4}\b"
        )
        self.cta_pattern: Pattern[str] = re.compile(
            r"\b(visit|go to|check out|head over|sign up|start today|start now|use code|offer|deal|free trial)\b",
            re.I,
        )
        self.transition_pattern: Pattern[str] = re.compile(
            r"\b(back to the show|after the break|stay tuned|we'll be right back|now back)\b",
            re.I,
        )
        self.self_promo_pattern: Pattern[str] = re.compile(
            r"\b(my|our)\s+(book|course|newsletter|fund|patreon|substack|community|platform)\b",
            re.I,
        )
        # Scout-only extras. Off by default so production highlight/analyze stay
        # identical. These cover phrases chapter-filter already knows about that
        # the production neighbor-expansion regexes do not.
        self.sponsor_pattern: Pattern[str] = re.compile(
            r"\b(sponsored by|brought to you by|this episode is sponsored|"
            r"paid partnership|our sponsor)\b",
            re.I,
        )
        self.ad_break_pattern: Pattern[str] = re.compile(
            r"\b(ad break|a word from our sponsor|after these messages|"
            r"advertisement)\b",
            re.I,
        )

    def _core_patterns(self) -> list[Pattern[str]]:
        return [
            self.url_pattern,
            self.promo_pattern,
            self.phone_pattern,
            self.cta_pattern,
            self.transition_pattern,
            self.self_promo_pattern,
        ]

    def _active_patterns(self) -> list[Pattern[str]]:
        patterns = self._core_patterns()
        if self.include_scout_extras:
            patterns.extend([self.sponsor_pattern, self.ad_break_pattern])
        return patterns

    def has_cue(self, text: str) -> bool:
        return bool(
            self.url_pattern.search(text)
            or self.promo_pattern.search(text)
            or self.phone_pattern.search(text)
            or self.cta_pattern.search(text)
        )

    def analyze(self, text: str) -> dict[str, bool]:
        signals = {
            "url": bool(self.url_pattern.search(text)),
            "promo": bool(self.promo_pattern.search(text)),
            "phone": bool(self.phone_pattern.search(text)),
            "cta": bool(self.cta_pattern.search(text)),
            "transition": bool(self.transition_pattern.search(text)),
            "self_promo": bool(self.self_promo_pattern.search(text)),
        }
        if self.include_scout_extras:
            signals["sponsor"] = bool(self.sponsor_pattern.search(text))
            signals["ad_break"] = bool(self.ad_break_pattern.search(text))
        return signals

    def has_strong_cue(self, text: str) -> bool:
        """Match AdClassifier neighbor-expansion strong-cue logic."""
        signals = self.analyze(text)
        return any(signals.get(key, False) for key in STRONG_CUE_KEYS)

    def score(
        self, text: str, weights: dict[str, float] | None = None
    ) -> tuple[float, dict[str, bool]]:
        """Weighted sum of analyze() flags. Returns (score, signals)."""
        signals = self.analyze(text)
        active_weights = weights or DEFAULT_SIGNAL_WEIGHTS
        total = 0.0
        for key, fired in signals.items():
            if fired:
                total += active_weights.get(key, 0.0)
        return total, signals

    def highlight_cues(self, text: str) -> str:
        """
        Highlights detected cues in the text by wrapping them in *** ***.
        Useful for drawing attention to cues in LLM prompts.
        """
        matches: list[tuple[int, int]] = []
        for pattern in self._active_patterns():
            for match in pattern.finditer(text):
                matches.append(match.span())

        if not matches:
            return text

        # Sort by start, then end (descending) to handle containment
        matches.sort(key=lambda x: (x[0], -x[1]))

        # Merge overlapping intervals
        merged: list[tuple[int, int]] = []
        if matches:
            curr_start, curr_end = matches[0]
            for next_start, next_end in matches[1:]:
                if next_start < curr_end:  # Overlap
                    curr_end = max(curr_end, next_end)
                else:
                    merged.append((curr_start, curr_end))
                    curr_start, curr_end = next_start, next_end
            merged.append((curr_start, curr_end))

        # Reconstruct string backwards to avoid index shifting
        result_parts = []
        last_idx = len(text)

        for start, end in reversed(merged):
            result_parts.append(text[end:last_idx])  # Unchanged suffix
            result_parts.append(" ***")
            result_parts.append(text[start:end])  # The match
            result_parts.append("*** ")
            last_idx = start

        result_parts.append(text[:last_idx])  # Remaining prefix

        return "".join(reversed(result_parts))
