"""Per-feed episode title exclusions (keep unwanted episodes from auto-processing).

Each comma-separated phrase is matched case-insensitively against the title:

* without ``*`` it matches anywhere in the title (``trailer``);
* with ``*`` it must match the whole title, ``*`` standing for any run of
  characters, so ``trailer*`` means "starts with", ``*rerun`` means
  "ends with" and ``*best*of*`` means "contains these in this order".

Only ``*`` is special; every other character, including ``?`` and ``[``,
matches itself.
"""

from typing import Any


def parse_title_exclude_strings(value: str | None) -> list[str]:
    """Split a comma-separated exclusion list into lower-cased phrases."""
    if not value:
        return []
    return [part.strip().casefold() for part in value.split(",") if part.strip()]


def normalize_title_exclude_strings(value: str | None) -> str | None:
    """Tidy a user-supplied list for storage; blank input clears it."""
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return ",".join(parts) or None


def _wildcard_match(pattern: str, text: str) -> bool:
    """Match all of ``text`` against ``pattern``, where ``*`` is any run of characters.

    Iterative matching that backtracks only to the most recent ``*``, so it runs
    in O(len(pattern) * len(text)) whatever the pattern looks like.
    """
    p = t = 0
    star = -1
    star_t = 0
    while t < len(text):
        if p < len(pattern) and pattern[p] == "*":
            star = p
            star_t = t
            p += 1
        elif p < len(pattern) and pattern[p] == text[t]:
            p += 1
            t += 1
        elif star != -1:
            p = star + 1
            star_t += 1
            t = star_t
        else:
            return False
    while p < len(pattern) and pattern[p] == "*":
        p += 1
    return p == len(pattern)


def _phrase_matches(phrase: str, folded_title: str) -> bool:
    if "*" in phrase:
        return _wildcard_match(phrase, folded_title)
    return phrase in folded_title


def is_title_excluded(feed: Any, title: str | None) -> bool:
    """Return True when ``title`` matches one of the feed's exclusion phrases."""
    phrases = parse_title_exclude_strings(
        getattr(feed, "episode_title_exclude_strings", None)
    )
    if not phrases or not title:
        return False
    folded = title.strip().casefold()
    return any(_phrase_matches(phrase, folded) for phrase in phrases)
