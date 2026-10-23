"""Sponsor/cue lexicon for $0 ad spotting.

Company names + Whisper-tolerant cue phrases. TUNE_NOTES record which
original-10 failures motivated a phrase so holdout overclaim is visible.
Show IDs are only in TUNE_NOTES, not in match logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from podcast_processor.quote_anchor import normalize_tokens


@dataclass(frozen=True)
class LexiconTuneNote:
    item: str
    motivated_by: str
    tuned_on_original10: bool


# Multi-word cues. Matching is Whisper-tolerant (token fold + insertions).
CUE_PHRASES: tuple[str, ...] = (
    "brought to you by",
    "this episode is sponsored",
    "this episode is brought to you",
    "this episode is brought",
    "sponsored by",
    "this message comes from",
    "support for this podcast comes from",
    "support for this show comes from",
    "support for this npr comes from",
    "support for npr comes from",
    "support comes from",
    "a word from our sponsor",
    "paid partnership",
    "paid partner",
    "our sponsor",
    "lead sponsor",
    "terms apply",
    "after the break",
    "we'll be right back",
    "we will be right back",
    "stay tuned",
    "back to the show",
    "and we're back",
    "promo code",
    "use code",
    "use promo",
    "dot com",
    "dot org",
    "dot net",
    "dot ca",
    "this week on",
    "listen now on",
    "listen now to",
    "listen to",
    "listen on the npr app",
    "listen on the",
    "on the npr app",
    "npr app",
    "wherever you get your podcasts",
    "wherever you listen",
    "planet money plus",
    "npr plus",
    "donate npr",
    "donate at",
    # Membership-shaped; bare "your support" also hits thank-yous with no
    # CTA, offer, or plug. Keep the 10s min.
    "your support empowers",
    "your support keeps",
    "your support makes",
    "relies on your support",
    "join the community",
    "public media",
    "makes this work possible",
    "keep public media public",
    "presented by",
    "this is a paid",
    "see website for details",
    "select states",
    "gambling problem",
    "21 plus",
    "new york times app",
    "the shows tab",
    "follow up first",
    "follow a show",
    "live show",
    "life partner",
    "this american life partner",
    "sign up today",
    "book a demo",
    "free download",
    "free trial",
    "slash",
    # Former ENABLE_SPOT_PLATFORM_CTA extras (genuine ad cues).
    "listen ad-free",
    "listen ad free",
    "play responsibly",
    "on patreon",
    "support the show on patreon",
    # Former ENABLE_SPOT_LEXICON_SELFPROMO extras (genuine ad cues).
    "support for the show comes from",
    "listen via the npr app",
    "listen via the",
    "weekly newsletter",
    "our newsletter",
    "my weekly newsletter",
    "subscribe to my weekly",
    "sign up for our newsletter",
    "follow us on youtube",
    "follow us on spotify",
    "please follow us",
    "drink ag one",
    "ag one",
    "pop culture happy hour",
    "culture happy hour",
    "sunday story",
    "this week on the sunday story",
)

# Common podcast advertisers + sister-show / app / membership names.
# Folded alnum match; multiword names also match as phrases.
SPONSOR_NAMES: tuple[str, ...] = (
    "shopify",
    "squarespace",
    "betterhelp",
    "audible",
    "ziprecruiter",
    "indeed",
    "rocket money",
    "mint mobile",
    "progressive",
    "geico",
    "state farm",
    "hellofresh",
    "factor",
    "stamps.com",
    "simplisafe",
    "ancestry",
    "athletic greens",
    "ag1",
    "lmnt",
    "liquid iv",
    "bombas",
    "warby parker",
    "netsuite",
    "threatlocker",
    "threat locker",
    "doppel",
    "sinch",
    "withings",
    "scanwatch",
    "freestyle",
    "fanduel",
    "fan duel",
    "the zone",
    "nfl game pass",
    "cornerpiece",
    "corner piece",
    "aarp",
    "capella",
    "betterment",
    "carvana",
    "zillow",
    "linkedin",
    "microsoft",
    "intuit",
    "turbotax",
    "credit karma",
    "sofi",
    "peaksaver",
    "peak saver",
    "sources and methods",
    "npr politics podcast",
    "npr politics",
    "ted radio hour",
    "fresh air",
    "park predators",
    "so supernatural",
    "wait wait",
    "weight wait",
    "weight way",
    "up first",
    "throughline",
    "how i built this",
    "this american life",
    "new york times",
    "donate.npr.org",
    "npr.org",
    "threatlocker.com",
    "doppel.com",
    "withings.com",
    "thezone.com",
    "the zone.com",
    "shopify.com",
    "netsuite.com",
    "patreon",
    "ag one",
    "sunday story",
    "pop culture happy hour",
)

URL_TLDS = frozenset({"com", "org", "net", "io", "fm", "co"})

# Historical names kept as aliases of the main bag so older experiment
# imports still resolve. They are no longer flag-gated.
PLATFORM_CTA_PHRASES: tuple[str, ...] = (
    "listen ad-free",
    "listen ad free",
    "play responsibly",
    "on patreon",
    "support the show on patreon",
)
PLATFORM_CTA_NAMES: tuple[str, ...] = ("patreon",)
SELFPROMO_CUE_PHRASES: tuple[str, ...] = (
    "support for the show comes from",
    "listen via the npr app",
    "listen via the",
    "weekly newsletter",
    "our newsletter",
    "my weekly newsletter",
    "subscribe to my weekly",
    "sign up for our newsletter",
    "follow us on youtube",
    "follow us on spotify",
    "please follow us",
    "drink ag one",
    "ag one",
    "pop culture happy hour",
    "culture happy hour",
    "sunday story",
    "this week on the sunday story",
)
SELFPROMO_NAMES: tuple[str, ...] = (
    "ag one",
    "sunday story",
    "pop culture happy hour",
)

TUNE_NOTES = (
    LexiconTuneNote(
        "your support empowers / keeps / makes / relies on your support / donate npr / public media",
        "npr_up_first 0-26 and 72-92 membership; planet_money 0-25",
        True,
    ),
    LexiconTuneNote(
        "this week on / npr app / wherever you get your podcasts",
        "npr_wait_wait 0-26 Politics; planet_money 1216 Up First / Ted Radio Hour",
        True,
    ),
    LexiconTuneNote(
        "sources and methods / wait wait whisper variants",
        "npr_up_first 868 and planet_money 1922 sister-show; Whisper Weight-Way",
        True,
    ),
    LexiconTuneNote(
        "park predators / so supernatural / new york times app",
        "crime_junkie sister plugs; serial Shows tab",
        True,
    ),
    LexiconTuneNote(
        "netsuite / threatlocker / doppel / withings / freestyle",
        "darknet_diaries and wtf_maron / crime_junkie host-reads (mined gold)",
        True,
    ),
    LexiconTuneNote(
        "the zone / fanduel / cornerpiece / life partner",
        "holdout names listed for production recall; not used to retune original-10",
        False,
    ),
    LexiconTuneNote(
        "listen ad-free / play responsibly / patreon",
        "2026-10-12 Boyle opening raffle + Patreon closer; not orig10",
        False,
    ),
    LexiconTuneNote(
        "support for the show comes from / newsletter / follow us on youtube / ag one",
        "2026-10-20 1424 AG1 open, 1426/1432/1434 first-party CTA; not orig10",
        False,
    ),
    LexiconTuneNote(
        "listen via the npr app / culture happy hour / sunday story",
        "2026-10-20 1425 Happy Hour teaser, 1433 Sunday Story; not orig10",
        False,
    ),
    LexiconTuneNote(
        "dotted .ca in URL_RE / dot ca cue",
        "2026-10-21 Prof G 1437 Chevrolet.ca tail DAI; not orig10. Bare ca still out of URL_TLDS.",
        False,
    ),
    LexiconTuneNote(
        "drop bare your support",
        "2026-10-22 Prof G 1437 awards thank-you (not an ad); membership still spotted via empowers/keeps/makes/relies + donate/public media. Not orig10.",
        False,
    ),
)


def fold_alnum(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def phrase_tokens(phrase: str) -> list[str]:
    return normalize_tokens(phrase.replace(".", " "))


def name_folds() -> tuple[str, ...]:
    return tuple(
        fold_alnum(name) for name in SPONSOR_NAMES if len(fold_alnum(name)) >= 4
    )
