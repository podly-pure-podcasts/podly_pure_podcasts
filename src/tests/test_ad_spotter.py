"""$0 lexicon spotter: cues, sponsor names, Whisper variants, clustering."""

from __future__ import annotations

from podcast_processor.ad_spotter import (
    gold_misses,
    repeated_ngrams,
    spot_candidates,
    spot_hits,
)
from podcast_processor.quote_anchor import WordTiming
from podcast_processor.sponsor_lexicon import URL_TLDS


def _words(text: str, t0: float = 0.0, dt: float = 0.2) -> list[WordTiming]:
    words: list[WordTiming] = []
    t = t0
    for raw in text.split():
        end = t + dt
        words.append(WordTiming(word=raw, start=t, end=end))
        t = end
    return words


def test_spots_donate_and_support_membership() -> None:
    words = _words("Your support empowers us. Give at donate.npr.org and thank you.")
    hits = spot_hits(words)
    kinds = {h.kind for h in hits}
    cues = {h.cue for h in hits}
    assert "cue" in kinds or "url" in kinds or "sponsor" in kinds
    assert any("support" in c or "donate" in c or c in {"url", "tld"} for c in cues)
    assert any(h.kind == "cue" and h.cue == "your support empowers" for h in hits)


def test_membership_your_support_keeps_and_relies() -> None:
    keeps = spot_hits(
        _words("Your support keeps our reporters on the ground holding power.")
    )
    relies = spot_hits(
        _words(
            "We're a nonprofit that relies on your support, which means we can report."
        )
    )
    assert any(h.kind == "cue" and h.cue == "your support keeps" for h in keeps)
    assert any(h.kind == "cue" and h.cue == "relies on your support" for h in relies)


def test_awards_thank_you_is_not_a_support_cue() -> None:
    # Thanking listeners / celebrating an award with no CTA, offer, or plug.
    words = _words(
        "The results of the signal awards are in and we won, thanks to "
        "your support and your votes, best daily podcast."
    )
    hits = spot_hits(words)
    assert not any(h.kind == "cue" and "your support" in h.cue for h in hits)


def test_spots_this_week_on_sister_show() -> None:
    words = _words("This week on Sources and Methods Defense Secretary Pete Hegseth")
    hits = spot_hits(words)
    assert any(
        h.kind in {"cue", "sponsor"} and ("this week on" in h.cue or "sources" in h.cue)
        for h in hits
    )


def test_spots_netsuite_and_spoken_url() -> None:
    words = _words(
        "This episode is sponsored by NetSuite. Get the guide at netsuite.com slash darknet."
    )
    hits = spot_hits(words)
    kinds = {h.kind for h in hits}
    assert "cue" in kinds
    assert "sponsor" in kinds or "url" in kinds


def test_spots_spelled_doppel() -> None:
    words = _words("Learn more at doppel.com that's spelled D-O-P-P-E-L Doppel.com.")
    hits = spot_hits(words)
    assert any(h.kind == "sponsor" and "doppel" in h.cue for h in hits)


def test_spots_listen_to_sister_show() -> None:
    words = _words("Listen to So Supernatural wherever you get your podcasts.")
    hits = spot_hits(words)
    assert any(
        "listen" in h.cue or "supernatural" in h.cue or "wherever" in h.cue
        for h in hits
    )


def test_cluster_nearby_hits() -> None:
    words = _words(
        "Support comes from NetSuite. Visit netsuite.com slash darknet. And we're back.",
        t0=100.0,
    )
    cands, stats = spot_candidates(words)
    assert stats.n_hits >= 2
    assert len(cands) == 1
    assert cands[0].end > cands[0].start


def test_gold_misses_unrecoverable() -> None:
    words = _words("Good morning everyone. Here's the news from Washington.")
    cands, _ = spot_candidates(words)
    missed = gold_misses(
        [(0.0, 8.0, "npr_up_first", "Good morning everyone. Here's the news.")],
        cands,
    )
    assert len(missed) == 1
    assert missed[0]["show_id"] == "npr_up_first"


def test_ca_tld_not_in_url_tlds() -> None:
    # Bare `ca` is English-dense (Canada / ca.); do not add it as a TLD
    # token. `net` already false-spots "net debt".
    assert "ca" not in URL_TLDS
    assert "net" in URL_TLDS


def test_dotted_ca_url_is_a_hit() -> None:
    words = _words("Discover yours at Chevrolet.ca. Canada is north of here.")
    hits = spot_hits(words)
    assert any(h.kind == "url" for h in hits)
    # Spoken country name must not become a TLD token hit.
    assert not any(h.kind == "url" and h.cue == "tld" for h in hits)


def test_dot_ca_cue() -> None:
    words = _words("Find the deal at chevrolet dot ca today folks")
    hits = spot_hits(words)
    assert any(h.kind == "cue" and h.cue == "dot ca" for h in hits)


def test_repeated_ngrams_across_episodes() -> None:
    a = _words("This week on Sources and Methods more news today folks")
    b = _words("Later this week on Sources and Methods we talk again")
    phrases = repeated_ngrams({"ep1": a, "ep2": b}, n=4, min_episodes=2)
    assert any("this week on sources" in p for p in phrases)


def test_listen_cta_splits_later_sister_teaser() -> None:
    """Stacked sister teasers: listen-CTA then a later show cue is a new cluster."""
    words = _words(
        "Listen to the swing state podcast wherever you get your podcasts.", t0=80.0
    ) + _words("On culture happy hour we talk movies.", t0=95.0)
    cands, _ = spot_candidates(words)
    assert len(cands) == 2
    assert cands[0].end < 90.0
    assert cands[1].start >= 93.0
    assert any(h.cue == "wherever you get your podcasts" for h in cands[0].hits)
    assert any("happy hour" in h.cue for h in cands[1].hits)


def test_packed_listen_cta_stays_in_one_cluster() -> None:
    words = _words(
        "Listen via the npr app or wherever you get your podcasts.",
        t0=80.0,
    )
    cands, stats = spot_candidates(words)
    assert stats.n_hits >= 2
    assert len(cands) == 1


def test_paid_read_without_listen_cta_still_clusters() -> None:
    words = _words(
        "Support comes from NetSuite. Visit netsuite.com slash darknet. And we're back.",
        t0=100.0,
    )
    cands, stats = spot_candidates(words)
    assert stats.n_hits >= 2
    assert len(cands) == 1
