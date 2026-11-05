from __future__ import annotations

from podcast_processor.quote_anchor import (
    QuoteAd,
    SegmentSpan,
    WordTiming,
    fallback_segment_edge,
    match_quote_tokens,
    match_quotes_in_order,
    match_rate,
    normalize_tokens,
    resolve_ads,
    token_edit_distance,
    word_index_range,
)


def _words(*pairs: tuple[str, float, float]) -> list[WordTiming]:
    return [WordTiming(word=w, start=s, end=e) for w, s, e in pairs]


def test_normalize_and_edit_distance() -> None:
    assert normalize_tokens("Use Code SAVE-20!") == ["use", "code", "save", "20"]
    assert token_edit_distance(["a", "b", "c"], ["a", "b", "c"]) == 0
    assert token_edit_distance(["a", "b", "c"], ["a", "x", "c"]) == 1


def test_url_and_spellout_tokens_match_quote() -> None:
    """Lexicon lock keeps Shopify.com / S-I-N-C-H as one word; still match."""
    shop = _words(
        ("That's", 1930.89, 1931.33),
        ("Shopify.com.", 1931.33, 1932.03),
        ("Go", 1932.03, 1932.40),
        ("to", 1932.40, 1932.55),
        ("Shopify.com", 1932.55, 1933.20),
        ("today", 1933.20, 1933.60),
    )
    hit = match_quote_tokens(shop, "That's Shopify.com. Go to Shopify.com today")
    assert hit is not None
    assert shop[hit[0]].word == "That's"
    assert shop[hit[1] - 1].word == "today"
    assert hit[2] >= 0.99

    spelled = _words(
        ("that's", 2686.6, 2686.9),
        ("spelled", 2686.9, 2687.2),
        ("S-I-N-C-H", 2687.2, 2688.4),
        ("SINCH.com.", 2688.4, 2689.3),
    )
    end = match_quote_tokens(spelled, "that's spelled S-I-N-C-H SINCH.com.")
    assert end is not None
    assert spelled[end[0]].word == "that's"
    assert spelled[end[1] - 1].word == "SINCH.com."
    assert end[2] >= 0.99


def test_exact_quote_match() -> None:
    words = _words(
        ("hello", 0.0, 0.3),
        ("this", 0.3, 0.5),
        ("episode", 0.5, 0.9),
        ("is", 0.9, 1.0),
        ("sponsored", 1.0, 1.5),
        ("by", 1.5, 1.7),
        ("netsuite", 1.7, 2.2),
        ("thanks", 2.2, 2.5),
    )
    hit = match_quote_tokens(words, "this episode is sponsored by netsuite")
    assert hit is not None
    start, end, score = hit
    assert words[start].word == "this"
    assert words[end - 1].word == "netsuite"
    assert score == 1.0


def test_paraphrase_ish_quote_match() -> None:
    words = _words(
        ("this", 10.0, 10.2),
        ("episode", 10.2, 10.5),
        ("is", 10.5, 10.6),
        ("sponsored", 10.6, 11.1),
        ("by", 11.1, 11.2),
        ("acme", 11.2, 11.5),
        ("dot", 11.5, 11.6),
        ("com", 11.6, 11.8),
    )
    hit = match_quote_tokens(words, "this episode is sponsored by acme")
    assert hit is not None
    assert hit[2] >= 0.72
    assert words[hit[0]].word == "this"
    assert words[hit[1] - 1].word in {"acme", "com"}


def test_repeated_phrase_resolves_in_order() -> None:
    words = _words(
        ("first", 0.0, 0.4),
        ("use", 1.0, 1.2),
        ("code", 1.2, 1.4),
        ("save20", 1.4, 1.9),
        ("now", 2.0, 2.2),
        ("show", 30.0, 30.4),
        ("use", 50.0, 50.2),
        ("code", 50.2, 50.4),
        ("save20", 50.4, 50.9),
        ("again", 51.0, 51.3),
    )
    ads = [
        QuoteAd(
            start_quote="use code save20",
            end_quote="use code save20",
            content_type="promotional_external",
            confidence=0.9,
        ),
        QuoteAd(
            start_quote="use code save20",
            end_quote="use code save20",
            content_type="promotional_external",
            confidence=0.9,
        ),
    ]
    ordered = match_quotes_in_order(words, ads)
    assert ordered[0][1] is not None
    assert ordered[1][1] is not None
    assert words[ordered[0][1][0]].start == 1.0
    assert words[ordered[1][1][0]].start == 50.0


def test_start_only_grows_back_across_leftover_eof_chunk() -> None:
    """Live Indicator 2026-10-07: leftover 1-seg chunk after a sister-show."""
    words = _words(
        ("This", 632.9, 633.2),
        ("election", 633.2, 633.6),
        ("season.", 633.6, 634.0),
        ("Follow", 648.7, 649.0),
        ("up", 649.0, 649.2),
        ("first.", 649.2, 654.4),
        ("Midlife", 654.4, 654.8),
        ("brings", 654.8, 655.2),
        ("changes.", 655.2, 656.5),
        ("Your", 656.5, 656.8),
        ("turn.", 656.8, 661.4),
        ("Find", 667.1, 667.4),
        ("it", 667.4, 667.6),
        ("on", 667.6, 667.8),
        ("the", 667.8, 668.0),
        ("NPR", 668.0, 668.3),
        ("app.", 668.3, 672.8),
        ("Head", 672.8, 673.1),
        ("comes", 673.1, 673.4),
        ("from", 673.4, 673.7),
        ("NPR", 673.7, 674.0),
        ("sponsor", 674.0, 674.4),
        ("AARP.", 674.4, 675.0),
    )
    segments = [
        SegmentSpan(622.4, 626.6, "It was fact checked by Sierra Wattas"),
        SegmentSpan(626.6, 632.9, "of NPR."),
        SegmentSpan(632.9, 638.2, "This election season you can streamline your news"),
        SegmentSpan(
            648.7,
            654.4,
            "Follow up first on the NPR app or wherever you get your podcasts.",
        ),
        SegmentSpan(654.4, 656.5, "Midlife brings a lot of changes."),
        SegmentSpan(656.5, 661.4, "Your turn with Alas and Aubrey is a new podcast"),
        SegmentSpan(
            661.4, 667.1, "From health and relationships to creativity and purpose"
        ),
        SegmentSpan(
            667.1,
            672.8,
            "With your turn, find it on the NPR app or wherever you get your podcasts.",
        ),
        SegmentSpan(672.8, 675.0, "Head comes from NPR sponsor AARP."),
    ]
    ad = QuoteAd(
        start_quote="Head comes from NPR sponsor AARP",
        end_quote="Head comes from NPR sponsor AARP",
        content_type="promotional_external",
        confidence=0.95,
    )
    matches = resolve_ads(
        [ad],
        words,
        segments,
        chunk_start=672.8,
        chunk_end=675.0,
        stop_before=652.485,
    )
    assert matches[0].dropped is False
    assert matches[0].method == "word"
    assert abs(matches[0].start - 654.4) < 1e-6
    assert abs(matches[0].end - 675.0) < 1e-6
    assert matches[0].start >= 652.485


def test_start_only_back_stops_at_prior_match() -> None:
    words = _words(
        ("show", 640.0, 640.5),
        ("content.", 640.5, 641.0),
        ("This", 641.0, 641.3),
        ("week", 641.3, 641.6),
        ("on", 641.6, 641.9),
        ("Sister.", 641.9, 650.0),
        ("Head", 650.0, 650.3),
        ("comes", 650.3, 650.6),
        ("from", 650.6, 650.9),
        ("AARP.", 650.9, 652.0),
    )
    segments = [
        SegmentSpan(640.0, 641.0, "show content."),
        SegmentSpan(
            641.0, 650.0, "This week on Sister Show wherever you get your podcasts."
        ),
        SegmentSpan(650.0, 652.0, "Head comes from NPR sponsor AARP."),
    ]
    ad = QuoteAd(
        start_quote="Head comes from NPR sponsor AARP",
        end_quote="Head comes from NPR sponsor AARP",
        content_type="promotional_external",
        confidence=0.95,
    )
    matches = resolve_ads(
        [ad],
        words,
        segments,
        chunk_start=650.0,
        chunk_end=652.0,
        stop_before=641.0,
    )
    assert matches[0].start == 641.0
    assert matches[0].end == 652.0


def test_start_only_grows_through_adjacent_segments() -> None:
    words = _words(
        ("this", 1921.8, 1922.2),
        ("week", 1922.2, 1922.6),
        ("on", 1922.6, 1923.0),
        ("sources", 1923.0, 1923.4),
        ("and", 1923.4, 1923.8),
        ("methods", 1923.8, 1924.2),
        ("defense", 1924.2, 1924.6),
        ("secretary", 1924.6, 1925.2),
        ("speaks.", 1925.2, 1925.7),
        ("we", 1925.8, 1926.0),
        ("are", 1926.0, 1926.2),
        ("no", 1926.2, 1926.4),
        ("longer", 1926.4, 1926.8),
        ("woke.", 1926.8, 1928.0),
    )
    segments = [
        SegmentSpan(
            1921.8,
            1925.7,
            "This week on Sources and Methods Defense Secretary speaks.",
        ),
        SegmentSpan(1925.8, 1928.0, "We are no longer woke."),
        SegmentSpan(1940.0, 1944.0, "Power is up for grabs in Wisconsin."),
    ]
    ad = QuoteAd(
        start_quote="This week on Sources and Methods Defense",
        end_quote="totally missing closer phrase here",
        content_type="educational/self_promo",
        confidence=0.95,
    )
    matches = resolve_ads([ad], words, segments, chunk_start=1920.0, chunk_end=1950.0)
    assert matches[0].dropped is False
    assert matches[0].method == "word"
    assert matches[0].start == 1921.8
    assert matches[0].end == 1928.0


def test_start_quote_takes_earliest_fuzzy_match() -> None:
    words = _words(
        ("like", 250.3, 250.5),
        ("you", 250.5, 250.7),
        ("everywhere", 250.7, 251.1),
        ("supports", 251.1, 251.4),
        ("cutting", 251.4, 251.7),
        ("edge", 251.7, 251.9),
        ("research", 251.9, 252.3),
        ("show", 300.0, 300.3),
        ("like", 322.3, 322.5),
        ("you", 322.5, 322.7),
        ("everywhere", 322.7, 323.1),
        ("supports", 323.1, 323.4),
        ("cutting", 323.4, 323.7),
        ("edge", 323.7, 323.9),
        ("research", 323.9, 324.3),
    )
    hit = match_quote_tokens(
        words, "like you everywhere supports cutting edge research"
    )
    assert hit is not None
    assert abs(words[hit[0]].start - 250.3) < 1e-6
    windowed = match_quote_tokens(
        words,
        "like you everywhere supports cutting edge research",
        search_from=8,
        search_to=len(words),
    )
    assert windowed is not None
    assert abs(words[windowed[0]].start - 322.3) < 1e-6


def test_end_quote_takes_latest_fuzzy_match() -> None:
    words = _words(
        ("visit", 10.0, 10.2),
        ("acme.com", 10.2, 10.6),
        ("today", 10.6, 10.9),
        ("and", 40.0, 40.2),
        ("visit", 50.0, 50.2),
        ("acme.com", 50.2, 50.6),
        ("today", 50.6, 50.9),
    )
    hit = match_quote_tokens(words, "visit acme.com today", prefer="latest")
    assert hit is not None
    assert abs(words[hit[0]].start - 50.0) < 1e-6
    assert words[hit[1] - 1].word == "today"


def test_fuzzy_match_tolerates_asr_typo() -> None:
    words = _words(
        ("like", 250.3, 250.5),
        ("you", 250.5, 250.7),
        ("everywere", 250.7, 251.1),
        ("supports", 251.1, 251.4),
        ("cutting", 251.4, 251.7),
        ("edge", 251.7, 251.9),
        ("research", 251.9, 252.3),
    )
    hit = match_quote_tokens(
        words, "like you everywhere supports cutting edge research"
    )
    assert hit is not None
    assert hit[2] >= 0.72
    assert words[hit[0]].word == "like"
    assert words[hit[1] - 1].word == "research"


def test_atp_st_jude_quotes_match_inside_sent_window() -> None:
    """ATP ~310-347 was quoted correctly; exact first-token search missed."""
    words = _words(
        ("like", 250.32, 250.63),
        ("you,", 250.63, 250.94),
        ("everywhere,", 250.94, 251.25),
        ("supports", 251.25, 251.56),
        ("cutting", 251.56, 251.87),
        ("edge", 251.87, 252.18),
        ("research", 252.18, 252.49),
        ("We'll", 321.71, 321.90),
        ("take", 321.90, 322.10),
        ("that", 322.10, 322.29),
        ("too.", 322.29, 322.49),
        ("Marco", 397.42, 397.70),
        ("Armin", 397.70, 397.97),
        ("tell", 397.97, 398.24),
        ("you", 398.24, 398.51),
        ("about", 398.51, 398.78),
        ("his", 398.78, 399.06),
        ("offset.", 399.06, 399.33),
    )
    ads = [
        QuoteAd(
            start_quote="like you everywhere supports cutting edge research",
            end_quote="Marco Armin tell you about his offset",
            content_type="promotional_external",
            confidence=0.95,
        )
    ]
    ordered = match_quotes_in_order(words, ads)
    assert ordered[0][1] is not None
    start_i, end_i, score = ordered[0][1]
    assert abs(words[start_i].start - 250.32) < 1e-6
    assert words[end_i - 1].word == "offset."
    assert score >= 0.72
    # A later confirm window that does not include the first copy still
    # cannot invent a start before its search range.
    later = match_quote_tokens(
        words,
        "like you everywhere supports cutting edge research",
        search_from=7,
        search_to=len(words),
    )
    assert later is None


def test_fuzzy_match_ignores_punctuation_and_case() -> None:
    words = _words(
        ("Like", 1.0, 1.2),
        ("you,", 1.2, 1.4),
        ("everywhere,", 1.4, 1.8),
        ("supports", 1.8, 2.1),
        ("cutting-edge", 2.1, 2.5),
        ("research!", 2.5, 2.9),
    )
    hit = match_quote_tokens(
        words, "LIKE YOU EVERYWHERE SUPPORTS CUTTING EDGE RESEARCH"
    )
    assert hit is not None
    assert hit[2] >= 0.72
    assert words[hit[0]].word == "Like"
    assert words[hit[1] - 1].word == "research!"


def test_no_match_returns_none() -> None:
    words = _words(
        ("good", 0.0, 0.3),
        ("morning", 0.3, 0.7),
        ("from", 0.7, 0.9),
        ("npr", 0.9, 1.2),
        ("news", 1.2, 1.5),
    )
    assert match_quote_tokens(words, "xyzzy plugh fnord") is None


def test_no_match_falls_back_to_segment_edge_and_never_drops() -> None:
    words = _words(
        ("hello", 0.0, 0.4),
        ("friends", 0.4, 0.8),
        ("welcome", 0.8, 1.2),
        ("back", 1.2, 1.5),
    )
    segments = [
        SegmentSpan(start=0.0, end=0.8, text="Hello friends"),
        SegmentSpan(start=0.8, end=1.5, text="welcome back to the show"),
        SegmentSpan(start=20.0, end=25.0, text="this episode is sponsored by Acme"),
        SegmentSpan(start=25.0, end=28.0, text="visit acme.com/podcast and save"),
    ]
    ad = QuoteAd(
        start_quote="this episode is sponsored by acme",
        end_quote="visit acme.com/podcast and save",
        content_type="promotional_external",
        confidence=0.95,
    )
    assert match_quote_tokens(words, ad.start_quote) is None
    fallback = fallback_segment_edge(ad, segments, chunk_start=18.0, chunk_end=30.0)
    assert fallback is not None
    assert fallback[0] == 20.0
    assert fallback[1] == 28.0

    matches = resolve_ads(
        [ad],
        words,
        segments,
        chunk_start=18.0,
        chunk_end=30.0,
    )
    assert len(matches) == 1
    assert matches[0].dropped is False
    assert matches[0].method == "segment_fallback"
    assert matches[0].start == 20.0
    assert matches[0].end == 28.0


def test_word_index_range_skips_forward_jump_leftover() -> None:
    """Reanchor leftover (Prof G 1432 Tesla at 4546s) must not empty a midroll window."""
    words = _words(
        ("hello", 0.0, 0.4),
        ("show", 1272.5, 1272.8),
        ("Tesla,", 4546.85, 4546.97),
        ("We'll", 1625.2, 1625.4),
        ("be", 1625.4, 1625.6),
        ("right", 1625.6, 1625.8),
        ("back", 1625.8, 1626.1),
        ("after", 1626.1, 1626.3),
        ("the", 1626.3, 1626.5),
        ("break.", 1626.5, 1626.8),
        ("We're", 1844.5, 1844.7),
        ("back", 1844.7, 1844.9),
        ("with", 1844.9, 1845.1),
        ("ProfG", 1845.1, 1845.5),
        ("Markets.", 1845.5, 1846.0),
    )
    lo, hi = word_index_range(words, 1554.7, 1904.3)
    assert hi > lo
    assert words[lo].word == "We'll"
    assert words[hi - 1].word == "Markets."
    ad = QuoteAd(
        start_quote="We'll be right back after the break",
        end_quote="We're back with ProfG Markets",
        content_type="promotional_external",
        confidence=0.95,
    )
    matches = resolve_ads(
        [ad],
        words,
        [
            SegmentSpan(
                start=1625.2, end=1626.8, text="We'll be right back after the break."
            ),
            SegmentSpan(
                start=1844.5, end=1846.0, text="We're back with ProfG Markets."
            ),
        ],
        chunk_start=1623.2,
        chunk_end=1835.9,
        word_from=lo,
        word_to=hi,
        time_start=1554.7,
        time_end=1904.3,
    )
    assert matches[0].method == "word"
    assert abs(matches[0].start - 1625.2) < 1e-6
    assert abs(matches[0].end - 1846.0) < 1e-6


def test_latest_end_quote_ignores_out_of_window_leftover() -> None:
    """prefer=latest must not jump to a later leftover inside the index span."""
    words = _words(
        ("wherever", 70.0, 70.3),
        ("you", 70.3, 70.5),
        ("get", 70.5, 70.7),
        ("your", 70.7, 70.9),
        ("podcasts.", 70.9, 71.3),
        ("wherever", 600.0, 600.3),
        ("you", 600.3, 600.5),
        ("get", 600.5, 600.7),
        ("your", 600.7, 600.9),
        ("podcasts.", 600.9, 601.3),
        ("show", 80.0, 80.4),
        ("resumes", 80.4, 80.9),
    )
    hit = match_quote_tokens(
        words,
        "wherever you get your podcasts",
        prefer="latest",
        time_start=0.0,
        time_end=135.0,
    )
    assert hit is not None
    assert abs(words[hit[0]].start - 70.0) < 1e-6
    unbounded = match_quote_tokens(
        words,
        "wherever you get your podcasts",
        prefer="latest",
    )
    assert unbounded is not None
    assert abs(words[unbounded[0]].start - 600.0) < 1e-6


def test_chunk_fallback_when_nothing_matches() -> None:
    words = _words(("hello", 0.0, 0.4), ("world", 0.4, 0.8))
    segments = [SegmentSpan(start=0.0, end=0.8, text="hello world")]
    ad = QuoteAd(
        start_quote="totally missing sponsor sentence here",
        end_quote="another missing closer sentence here",
        content_type="promotional_external",
        confidence=0.9,
    )
    matches = resolve_ads([ad], words, segments, chunk_start=5.0, chunk_end=12.0)
    assert len(matches) == 1
    assert matches[0].dropped is False
    assert matches[0].method == "chunk_fallback"
    assert matches[0].start == 5.0
    assert matches[0].end == 12.0
    assert match_rate(matches) == 0.0


def test_word_match_rate_is_one_when_all_hit() -> None:
    words = _words(
        ("this", 0.0, 0.2),
        ("episode", 0.2, 0.5),
        ("is", 0.5, 0.6),
        ("sponsored", 0.6, 1.0),
        ("by", 1.0, 1.1),
        ("acme", 1.1, 1.4),
        ("go", 1.4, 1.5),
        ("to", 1.5, 1.6),
        ("acme", 1.6, 1.9),
        ("dot", 1.9, 2.0),
        ("com", 2.0, 2.2),
    )
    ad = QuoteAd(
        start_quote="this episode is sponsored by acme",
        end_quote="go to acme dot com",
        content_type="promotional_external",
        confidence=0.9,
    )
    matches = resolve_ads([ad], words, [], chunk_start=0.0, chunk_end=3.0)
    assert matches[0].method == "word"
    assert match_rate(matches) == 1.0


def test_expand_outward_to_silence_stays_inside_bound() -> None:
    from podcast_processor.quote_anchor import expand_outward_to_silence

    start, end = expand_outward_to_silence(
        10.0,
        12.0,
        [(7.0, 8.0), (13.0, 14.0), (1.0, 2.0), (20.0, 21.0)],
        bound_start=6.0,
        bound_end=15.0,
    )
    assert start == 8.0
    assert end == 13.0


def test_expand_outward_no_silence_keeps_quote() -> None:
    from podcast_processor.quote_anchor import expand_outward_to_silence

    start, end = expand_outward_to_silence(
        10.0, 12.0, [], bound_start=4.0, bound_end=20.0
    )
    assert start == 10.0
    assert end == 12.0


def test_expand_outward_never_wider_than_bound() -> None:
    from podcast_processor.quote_anchor import expand_outward_to_silence

    start, end = expand_outward_to_silence(
        10.0,
        12.0,
        [(0.0, 1.0), (18.0, 19.0)],
        bound_start=9.0,
        bound_end=13.0,
    )
    assert start == 10.0
    assert end == 12.0


def test_expand_pad_then_snap_still_clipped() -> None:
    from podcast_processor.quote_anchor import expand_outward_to_silence

    start, end = expand_outward_to_silence(
        10.0,
        12.0,
        [(7.5, 8.0), (14.0, 14.5)],
        bound_start=8.5,
        bound_end=13.0,
        pad_seconds=2.0,
    )
    assert start == 8.5
    assert end == 13.0


def test_clip_cut_to_baseline_does_not_drop_new_ads() -> None:
    from podcast_processor.quote_anchor import clip_cut_to_baseline

    assert clip_cut_to_baseline(50.0, 60.0, [(0.0, 10.0)]) == (50.0, 60.0)
    assert clip_cut_to_baseline(8.0, 14.0, [(0.0, 12.0)]) == (8.0, 12.0)


def test_hybrid_uses_segment_edge_bound_from_resolve() -> None:
    words = _words(
        ("support", 8.0, 8.3),
        ("comes", 8.3, 8.6),
        ("from", 8.6, 8.9),
        ("acme", 9.0, 9.4),
        ("visit", 11.0, 11.3),
        ("acme", 11.3, 11.6),
        ("dot", 11.6, 11.8),
        ("com", 11.8, 12.0),
    )
    segments = [
        SegmentSpan(start=7.0, end=9.5, text="support comes from acme"),
        SegmentSpan(start=11.0, end=13.0, text="visit acme dot com thanks"),
    ]
    ad = QuoteAd(
        start_quote="comes from acme",
        end_quote="visit acme dot com",
        content_type="promotional_external",
        confidence=0.9,
    )
    matches = resolve_ads([ad], words, segments, chunk_start=7.0, chunk_end=13.0)
    assert matches[0].method == "word"
    assert matches[0].bound_start == 7.0
    assert matches[0].bound_end == 13.0


def test_segment_fallback_when_dai_missing_from_word_stream() -> None:
    """Word-timestamp Whisper dropped the midroll; segment transcript still has it."""
    words = _words(
        ("please.", 401.0, 401.2),
        ("Hey,", 435.98, 436.4),
        ("it's", 439.3, 439.5),
        ("Peter.", 439.7, 440.2),
        ("podcasts.", 456.0, 457.8),
    )
    segments = [
        SegmentSpan(404.36, 409.36, "This message comes from Wise, the smart way"),
        SegmentSpan(419.36, 427.36, "Keep public media public donate.npr.org"),
        SegmentSpan(439.36, 459.36, "Hey it's me Peter wherever you get your podcasts"),
    ]
    ad = QuoteAd(
        start_quote="This message comes from Wise, the smart",
        end_quote="wherever you get your podcasts",
        content_type="promotional_external",
        confidence=0.95,
    )
    matches = resolve_ads(
        [ad],
        words,
        segments,
        chunk_start=400.0,
        chunk_end=470.0,
        word_from=0,
        word_to=len(words),
    )
    assert matches[0].method == "segment_fallback"
    assert matches[0].start == 404.36
    assert matches[0].end == 459.36
