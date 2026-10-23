from __future__ import annotations

from podcast_processor.quote_anchor import QuoteAd, QuoteMatch, WordTiming
from podcast_processor.quote_lexicon import (
    lexical_cuts_from_matches,
    refine_quote_span,
    union_v1_v2_cuts,
)


def _words(*pairs: tuple[str, float, float]) -> list[WordTiming]:
    return [WordTiming(word=w, start=s, end=e) for w, s, e in pairs]


def test_phrase_forward_trim_removed() -> None:
    """LLM quotes are kept; string lead-in / after-the-break trim is gone."""
    words = _words(
        ("I'm", 700.0, 700.2),
        ("a", 700.2, 700.3),
        ("bluff", 700.3, 700.5),
        ("for", 700.5, 700.7),
        ("listener", 700.7, 700.9),
        ("game.", 700.9, 701.1),
        ("We'll", 701.2, 701.4),
        ("be", 701.4, 701.5),
        ("back", 701.5, 701.7),
        ("from", 701.8, 702.0),
        ("NPR.", 702.0, 702.3),
        ("Support", 704.0, 704.3),
        ("comes", 704.3, 704.5),
        ("from", 704.5, 704.7),
        ("our", 704.7, 704.9),
        ("sponsor.", 704.9, 705.3),
    )
    start, end = refine_quote_span(words, 700.0, 705.3)
    assert start == 700.0
    assert end == 705.3


def test_after_the_break_is_not_string_trimmed() -> None:
    words = _words(
        ("After", 1199.0, 1199.2),
        ("the", 1199.2, 1199.3),
        ("break,", 1199.3, 1199.5),
        ("a", 1199.6, 1199.7),
        ("fix", 1199.7, 1199.9),
        ("that", 1199.9, 1200.0),
        ("doesn't.", 1200.0, 1200.3),
        ("This", 1218.0, 1218.3),
        ("election", 1218.3, 1218.6),
        ("season,", 1218.6, 1219.0),
        ("streamline", 1219.0, 1219.4),
        ("your", 1219.4, 1219.6),
        ("news.", 1219.6, 1220.0),
    )
    start, end = refine_quote_span(words, 1199.0, 1220.0)
    assert start == 1199.0
    assert end == 1220.0


def test_deleted_string_cut_kwargs_are_ignored() -> None:
    words = _words(
        ("After", 1324.0, 1324.2),
        ("the", 1324.2, 1324.4),
        ("break,", 1324.4, 1324.7),
        ("our", 1324.8, 1325.0),
        ("thrilling", 1325.0, 1325.4),
        ("conclusion.", 1325.4, 1326.0),
        ("This", 1348.1, 1348.4),
        ("message", 1348.4, 1348.7),
        ("comes", 1348.7, 1349.0),
        ("from", 1349.0, 1349.2),
        ("Granger.", 1349.2, 1349.8),
        ("stop", 1360.0, 1360.3),
        ("by.", 1360.3, 1360.6),
    )
    start, end = refine_quote_span(
        words,
        1324.0,
        1360.6,
        bridge_trim_30=True,
        sister_stack_tail=True,
        sister_teaser_skip=True,
        resume_trim=True,
        closer_tail=True,
        backfill_leadin=True,
    )
    assert start == 1324.0
    assert end == 1360.6


def test_pull_start_across_closer_hole() -> None:
    # npr_up_first 868: credits/closer, long hole, sister-show.
    words = _words(
        ("executive", 0.0, 0.3),
        ("producer", 0.3, 0.6),
        ("is", 0.6, 0.8),
        ("Kelly", 0.8, 1.0),
        ("Dick.", 1.0, 1.3),
        ("Let's", 1.4, 1.6),
        ("join", 1.6, 1.8),
        ("us", 1.8, 1.9),
        ("again", 1.9, 2.1),
        ("tomorrow.", 2.1, 2.4),
        ("This", 20.0, 20.3),
        ("week", 20.3, 20.5),
        ("on", 20.5, 20.7),
        ("Sources", 20.7, 21.0),
        ("and", 21.0, 21.2),
        ("Methods", 21.2, 21.5),
    )
    start, end = refine_quote_span(words, 20.0, 21.5)
    assert abs(start - 2.4) < 1e-6
    assert end == 21.5


def test_opening_short_hole_does_not_pull() -> None:
    # npr_up_first 72.5: bumper, 4.7s hole, membership read.
    words = _words(
        ("Stay", 0.0, 0.2),
        ("with", 0.2, 0.4),
        ("us.", 0.4, 0.6),
        ("We'll", 0.7, 0.9),
        ("give", 0.9, 1.1),
        ("you", 1.1, 1.2),
        ("news", 1.2, 1.4),
        ("you", 1.4, 1.5),
        ("need", 1.5, 1.7),
        ("to", 1.7, 1.8),
        ("start", 1.8, 2.0),
        ("your", 2.0, 2.2),
        ("day.", 2.2, 2.5),
        ("A", 7.2, 7.5),
        ("free", 7.5, 7.8),
        ("press", 7.8, 8.1),
        ("is", 8.1, 8.3),
        ("a", 8.3, 8.4),
        ("critical", 8.4, 8.8),
        ("protection.", 8.8, 9.2),
    )
    start, end = refine_quote_span(words, 7.2, 9.2)
    assert start == 7.2
    assert end == 9.2


def test_extend_end_to_silence_in_wordless_gap() -> None:
    # darknet: CTA, then ~9s bed, then show.
    words = _words(
        ("guide", 0.0, 0.3),
        ("at", 0.3, 0.5),
        ("netsuite", 0.5, 1.0),
        (".com", 1.0, 1.4),
        ("slash", 1.4, 1.7),
        ("darknet.", 1.7, 2.2),
        ("I", 11.5, 11.8),
        ("just", 11.8, 12.0),
        ("came", 12.0, 12.2),
        ("back", 12.2, 12.4),
        ("from", 12.4, 12.6),
        ("Defcon.", 12.6, 13.0),
    )
    start, end = refine_quote_span(words, 0.0, 2.2, gaps=[(9.0, 11.4)])
    assert start == 0.0
    assert end == 9.0


def test_short_cta_music_uses_silence_end() -> None:
    words = _words(
        ("give", 0.0, 0.2),
        ("at", 0.2, 0.4),
        ("donate", 0.4, 0.7),
        (".npr", 0.7, 1.1),
        (".org.", 1.1, 1.5),
        ("This", 4.8, 5.1),
        ("is", 5.1, 5.3),
        ("Planet", 5.3, 5.6),
        ("Money", 5.6, 5.9),
        ("from", 5.9, 6.1),
        ("NPR.", 6.1, 6.4),
    )
    start, end = refine_quote_span(words, 0.0, 1.5, gaps=[(1.6, 4.6)])
    assert start == 0.0
    assert end == 4.6


def test_long_hole_pull_stops_at_previous_word_end() -> None:
    words = _words(
        ("This", 100.0, 100.3),
        ("is", 100.3, 100.5),
        ("Darknet", 100.5, 100.9),
        ("Diaries.", 100.9, 101.3),
        ("This", 118.0, 118.3),
        ("episode", 118.3, 118.6),
        ("is", 118.6, 118.8),
        ("sponsored", 118.8, 119.2),
        ("by", 119.2, 119.4),
        ("Acme.", 119.4, 119.8),
    )
    start, end = refine_quote_span(words, 118.0, 119.8)
    assert abs(start - 101.3) < 1e-6
    assert end == 119.8


def test_does_not_eat_show_ident_after_short_pause() -> None:
    words = _words(
        ("donate", 0.0, 0.3),
        (".npr", 0.3, 0.7),
        (".org.", 0.7, 1.1),
        ("This", 2.0, 2.3),
        ("is", 2.3, 2.5),
        ("Planet", 2.5, 2.8),
        ("Money", 2.8, 3.1),
        ("from", 3.1, 3.3),
        ("NPR.", 3.3, 3.6),
    )
    start, end = refine_quote_span(words, 0.0, 1.1, gaps=[(1.15, 1.9)])
    assert start == 0.0
    assert end == 1.1


def test_does_not_trim_a_leadin_ad() -> None:
    words = _words(
        ("This", 0.0, 0.2),
        ("episode", 0.2, 0.5),
        ("is", 0.5, 0.6),
        ("sponsored", 0.6, 1.0),
        ("by", 1.0, 1.1),
        ("NetSuite.", 1.1, 1.6),
        ("AI", 2.2, 2.4),
        ("isn't", 2.4, 2.6),
        ("just", 2.6, 2.8),
        ("opening", 2.8, 3.1),
        ("doors.", 3.1, 3.4),
    )
    start, end = refine_quote_span(words, 0.0, 3.4)
    assert start == 0.0
    assert end == 3.4


def test_preroll_snaps_to_zero() -> None:
    words = _words(
        ("This", 1.5, 1.8),
        ("episode", 1.8, 2.1),
        ("is", 2.1, 2.3),
        ("sponsored", 2.3, 2.7),
        ("by", 2.7, 2.9),
        ("Acme.", 2.9, 3.3),
    )
    start, end = refine_quote_span(words, 1.5, 3.3)
    assert start == 0.0
    assert end == 3.3


def test_wherever_outro_does_not_trim_opening() -> None:
    words = _words(
        ("Hey,", 0.0, 0.3),
        ("it's", 0.3, 0.5),
        ("Anna", 0.5, 0.8),
        ("from", 0.8, 1.0),
        ("The", 1.0, 1.1),
        ("Times.", 1.1, 1.4),
        ("Wherever", 2.2, 2.5),
        ("you", 2.5, 2.7),
        ("get", 2.7, 2.9),
        ("your", 2.9, 3.1),
        ("podcasts.", 3.1, 3.5),
        ("Yeah,", 4.6, 4.9),
        ("no,", 4.9, 5.1),
        ("this", 5.1, 5.3),
        ("is", 5.3, 5.4),
        ("the", 5.4, 5.5),
        ("show.", 5.5, 5.8),
    )
    start, _end = refine_quote_span(words, 0.0, 5.8)
    assert start == 0.0


def test_dai_bed_after_voicemail_bye_pulls() -> None:
    # holdout npr_indicator 422: 9s wordless DAI bed after "Bye-bye." then Wait Wait.
    words = _words(
        ("Thank", 421.0, 421.3),
        ("you", 421.3, 421.5),
        ("so", 421.5, 421.7),
        ("much.", 421.7, 422.0),
        ("Bye-bye.", 426.6, 426.8),
        ("Hey,", 435.98, 436.4),
        ("it's", 439.3, 439.5),
        ("me,", 439.5, 439.7),
        ("Peter.", 439.7, 440.2),
    )
    start, end = refine_quote_span(words, 435.98, 440.2)
    assert start == 435.98
    assert end == 440.2
    on_start, on_end = refine_quote_span(words, 435.98, 440.2, pull_dai_bed=True)
    assert abs(on_start - 426.8) < 1e-6
    assert on_end == 440.2


def test_credits_nine_second_hole_does_not_pull() -> None:
    # planet_money 1921: "thanks for listening" then 9.9s then sister-show.
    words = _words(
        ("Thanks", 1910.94, 1911.14),
        ("for", 1911.14, 1911.26),
        ("listening.", 1911.26, 1911.48),
        ("This", 1921.38, 1922.10),
        ("week", 1922.10, 1922.36),
        ("on", 1922.36, 1922.64),
        ("Sources.", 1922.64, 1923.14),
    )
    start, end = refine_quote_span(words, 1921.38, 1923.14)
    assert start == 1921.38
    assert end == 1923.14


def test_mid_episode_short_hole_does_not_pull() -> None:
    words = _words(
        ("end", 100.0, 100.3),
        ("of", 100.3, 100.5),
        ("scene.", 100.5, 100.8),
        ("When", 106.0, 106.3),
        ("the", 106.3, 106.5),
        ("holiday", 106.5, 106.8),
        ("shopping", 106.8, 107.1),
        ("starts.", 107.1, 107.4),
    )
    start, _end = refine_quote_span(words, 106.0, 107.4)
    assert start == 106.0


def test_cta_sentence_end_is_capped() -> None:
    words = _words(
        ("visit", 0.0, 0.2),
        ("acme", 0.2, 0.5),
        (".com", 0.5, 0.8),
        ("all", 0.9, 1.1),
        ("right", 1.1, 1.3),
        ("we", 1.3, 1.5),
        ("have", 1.5, 1.7),
        ("been", 1.7, 1.9),
        ("busy.", 20.0, 20.4),
    )
    _start, end = refine_quote_span(words, 0.0, 0.8)
    assert end == 0.8


def test_asymmetric_end_uses_bound() -> None:
    matches = [
        QuoteMatch(
            ad=QuoteAd(
                "this episode is sponsored",
                "visit acme.com",
                "promotional_external",
                0.9,
            ),
            start=1.5,
            end=3.3,
            method="word",
            score=1.0,
            bound_start=0.0,
            bound_end=8.0,
        )
    ]
    words = _words(
        ("This", 1.5, 1.8),
        ("episode", 1.8, 2.1),
        ("is", 2.1, 2.3),
        ("sponsored", 2.3, 2.7),
        ("by", 2.7, 2.9),
        ("Acme.", 2.9, 3.3),
    )
    pure = lexical_cuts_from_matches(matches, words, asymmetric_end=False)
    asym = lexical_cuts_from_matches(matches, words, asymmetric_end=True)
    assert pure[0][1] == 3.3
    assert asym[0][1] == 8.0
    assert pure[0][0] == 0.0
    assert asym[0][0] == 0.0


def test_union_takes_later_v1_start_and_later_v2_end() -> None:
    v2 = [(717.58, 821.9), (1883.26, 1913.58)]
    v1 = [(726.48, 747.76), (749.28, 821.9), (1890.25, 1913.58)]
    out = union_v1_v2_cuts(v2, v1)
    assert out[0][0] == 726.48
    assert out[0][1] == 821.9
    assert out[1][0] == 1890.25
    assert out[1][1] == 1913.58
