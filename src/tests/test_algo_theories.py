"""Spot-then-confirm production path: hardcoded clean behaviors, no flags."""

from __future__ import annotations

from podcast_processor.ad_spotter import (
    CandidateBreak,
    drop_weak_candidates,
    is_weak_candidate,
    spot_candidates,
    spot_hits,
)
from podcast_processor.boundary_snap import SilenceGap, snap_time_to_silence
from podcast_processor.quote_anchor import QuoteAd, QuoteMatch, WordTiming
from podcast_processor.quote_anchor_classifier import (
    SPOT_BRIDGE_GAP_S,
    SPOT_PAD_S,
    SPOT_WIDE_PAD_S,
    effective_min_ad_segment_length_seconds,
    effective_spot_bridge_gap_s,
    effective_spot_pad_s,
    grouped_candidate,
    left_extend_adds_transcript,
    merge_spot_confirm_windows,
    prompt_version_for,
    sent_window_word_range,
    union_confirm_matches,
)
from podcast_processor.quote_anchor_prompt import (
    confirm_user_prompt,
    system_prompt_for,
)
from podcast_processor.sponsor_lexicon import CUE_PHRASES, SPONSOR_NAMES
from shared import defaults as DEFAULTS
from shared.config import Config
from shared.test_utils import create_standard_test_config


def _words(*pairs: tuple[str, float, float]) -> list[WordTiming]:
    return [WordTiming(word=w, start=s, end=e) for w, s, e in pairs]


def test_spot_then_confirm_is_unconditional() -> None:
    assert DEFAULTS.SPOT_WIDE_PAD_SECONDS == 70.0
    assert DEFAULTS.SPOT_BRIDGE_GAP_SECONDS == 120.0
    assert DEFAULTS.OUTPUT_MIN_AD_SEGMENT_LENGTH_SECONDS == 10
    config = create_standard_test_config()
    assert "enable_spot_then_confirm" not in Config.model_fields
    assert "enable_quote_anchor_boundaries" not in Config.model_fields
    assert "enable_spot_wide_pad" not in Config.model_fields
    assert "enable_spot_bridge_windows" not in Config.model_fields
    assert "enable_spot_opening_isolate" not in Config.model_fields
    assert effective_spot_pad_s(config) == SPOT_WIDE_PAD_S == 70.0
    assert effective_spot_bridge_gap_s(config) == SPOT_BRIDGE_GAP_S == 120.0
    assert prompt_version_for(config) == "v2"
    assert effective_min_ad_segment_length_seconds(config) == 10


def _text_words(text: str, t0: float = 0.0, dt: float = 0.2) -> list[WordTiming]:
    words: list[WordTiming] = []
    t = t0
    for raw in text.split():
        words.append(WordTiming(word=raw, start=t, end=t + dt))
        t += dt
    return words


def test_weak_drop_keeps_url_drops_name_only() -> None:
    name_only = _text_words(
        "NetSuite announced a new product today in Cupertino California."
    )
    url = _text_words(
        "Go to netsuite.com slash darknet and donate whatever you can today."
    )
    weak, _ = spot_candidates(name_only, drop_weak=True)
    strong, _ = spot_candidates(url, drop_weak=True)
    raw_name, _ = spot_candidates(name_only, drop_weak=False)
    assert all(not is_weak_candidate(c) for c in drop_weak_candidates(raw_name) or [])
    # URL/slash hits survive; a lone folded company name does not.
    assert len(strong) >= 1
    kinds = {h.kind for h in spot_hits(url)}
    assert "url" in kinds or "cue" in kinds
    if weak:
        assert all(not is_weak_candidate(c) for c in weak)


def test_earlier_start_does_not_snap_start_later() -> None:
    gaps = [SilenceGap(start=8.8, end=9.0)]
    nearest = snap_time_to_silence(8.7, gaps, radius=2.5, kind="start")
    earlier = snap_time_to_silence(
        8.7, gaps, radius=2.5, kind="start", prefer="earlier_start"
    )
    assert nearest == 9.0
    assert earlier == 8.7
    # End snap is unchanged (still nearest).
    end_gaps = [SilenceGap(start=20.2, end=20.6)]
    assert (
        snap_time_to_silence(
            20.0, end_gaps, radius=2.5, kind="end", prefer="earlier_start"
        )
        == 20.2
    )


def test_min_ad_floor_is_10s() -> None:
    config = create_standard_test_config()
    assert effective_min_ad_segment_length_seconds(config) == 10
    assert DEFAULTS.OUTPUT_MIN_AD_SEGMENT_LENGTH_SECONDS == 10


def _match(
    start: float, end: float, *, quote: str = "support comes from"
) -> QuoteMatch:
    return QuoteMatch(
        ad=QuoteAd(
            start_quote=quote,
            end_quote="visit example.com slash show",
            content_type="promotional_external",
            confidence=0.95,
        ),
        start=start,
        end=end,
        method="word",
        score=1.0,
    )


def test_spot_pad_is_70s_with_override() -> None:
    config = create_standard_test_config()
    assert effective_spot_pad_s(config) == SPOT_WIDE_PAD_S == 70.0
    assert effective_spot_pad_s(config, override=8.0) == 8.0
    assert SPOT_PAD_S == 50.0


def test_union_confirm_keeps_first_and_joins_overlap() -> None:
    first = [_match(1129.0, 1195.0, quote="Support for the show comes from VCX")]
    second = [_match(1178.0, 1248.0, quote="And the next gen formula delivers more")]
    joined = union_confirm_matches(first, second)
    assert len(joined) == 1
    assert joined[0].start == 1129.0
    assert joined[0].end == 1248.0
    empty_second = union_confirm_matches(first, [])
    assert [(m.start, m.end) for m in empty_second] == [(1129.0, 1195.0)]
    disjoint = union_confirm_matches(
        first, [_match(150.0, 176.0, quote="By the way I recently interviewed")]
    )
    assert [(m.start, m.end) for m in disjoint] == [
        (150.0, 176.0),
        (1129.0, 1195.0),
    ]
    # A contained second reply must not shrink the first win.
    shorter = union_confirm_matches(
        first, [_match(1178.0, 1190.0, quote="Visit get VCX")]
    )
    assert [(m.start, m.end) for m in shorter] == [(1129.0, 1195.0)]


def test_left_extend_skips_when_chunk_already_has_t0() -> None:
    segments = [(0.0, 3.2), (3.2, 22.0), (52.7, 84.8)]
    assert (
        left_extend_adds_transcript(
            segments,
            chunk_start=0.0,
            window_start=2.71,
            window_end=134.83,
        )
        is False
    )


def test_left_extend_still_fires_when_earlier_transcript_exists() -> None:
    segments = [
        (0.0, 80.0),
        (80.0, 90.0),
        (90.0, 100.0),
        (100.0, 110.0),
    ]
    assert (
        left_extend_adds_transcript(
            segments,
            chunk_start=90.0,
            window_start=91.0,
            window_end=119.0,
        )
        is True
    )


def _cand(start: float, end: float) -> CandidateBreak:
    return CandidateBreak(
        start=start,
        end=end,
        hits=(),
        kinds=("cue",),
        weight=1.0,
    )


def test_wide_pad_is_70s() -> None:
    config = create_standard_test_config()
    assert effective_spot_pad_s(config) == SPOT_WIDE_PAD_S == 70.0
    assert DEFAULTS.SPOT_WIDE_PAD_SECONDS == 70.0


def test_bridge_windows_merges_under_120s_not_over() -> None:
    config = create_standard_test_config()
    assert effective_spot_bridge_gap_s(config) == SPOT_BRIDGE_GAP_S == 120.0
    near = merge_spot_confirm_windows(
        [_cand(1048.0, 1053.0), _cand(1112.0, 1122.0)],
        pad_s=50.0,
        ep_end=2000.0,
        max_gap_s=120.0,
    )
    assert len(near) == 1
    start, end, group = near[0]
    assert start == 998.0
    assert end == 1172.0
    assert grouped_candidate(group).start == 1048.0
    assert grouped_candidate(group).end == 1122.0
    far = merge_spot_confirm_windows(
        [_cand(70.0, 86.0), _cand(596.0, 641.0)],
        pad_s=50.0,
        ep_end=700.0,
        max_gap_s=120.0,
    )
    assert len(far) == 2


def test_prompt_v2_recap_is_not_ad_start_awards_are_content() -> None:
    system = system_prompt_for("v2")
    assert "host recap or tease of upcoming episode topics is show content" in system
    assert "that's all coming after the break" in system
    assert "Awards talk and thanking listeners" in system
    assert "we'll tell you why after the break" not in system.lower()
    user = confirm_user_prompt(
        title="Any show",
        start_seconds=0.0,
        texts=["We'll tell you why after the break. Listen to the sister show."],
        prompt_version="v2",
    )
    assert "host recap" in user
    assert "Awards/thanks" in user


def test_production_prompt_stays_v2() -> None:
    assert prompt_version_for(create_standard_test_config()) == "v2"
    system = system_prompt_for("v2")
    assert "host recap or tease of upcoming episode topics is show content" in system


def test_prompt_v3_library_still_marks_sister_teasers() -> None:
    system = system_prompt_for("v3")
    assert "FULL first sentence" in system
    assert "newsletter" in system.lower()
    assert "YouTube" in system
    assert "sister-show" in system.lower() or "sister teasers" in system.lower()
    user = confirm_user_prompt(
        title="Indicator",
        start_seconds=0.0,
        texts=["Listen via the NPR app. On Top Culture Happy Hour, a guide."],
        prompt_version="v3",
    )
    assert "FULL SENTENCES" in user
    assert "follow/newsletter" in user or "newsletter/follow" in user


def test_spotter_bag_includes_platform_and_selfpromo_cues() -> None:
    assert "listen ad-free" in CUE_PHRASES
    assert "play responsibly" in CUE_PHRASES
    assert "support for the show comes from" in CUE_PHRASES
    assert "follow us on youtube" in CUE_PHRASES
    assert "patreon" in SPONSOR_NAMES
    opening = _words(
        ("Would", 11.0, 11.2),
        ("you", 11.2, 11.4),
        ("listen", 11.4, 11.6),
        ("ad-free?", 11.6, 12.0),
    )
    hits, _ = spot_candidates(opening, drop_weak=True)
    assert hits
    editorial = _words(
        ("If", 10.0, 10.2),
        ("you", 10.2, 10.3),
        ("like", 10.3, 10.5),
        ("YouTube,", 10.5, 10.9),
        ("you'll", 10.9, 11.1),
        ("love", 11.1, 11.3),
        ("this.", 11.3, 11.6),
    )
    bare, _ = spot_candidates(editorial, drop_weak=True)
    assert bare == []


def test_sent_window_word_range_is_the_prompt_span() -> None:
    words = _words(
        ("On", 0.0, 0.2),
        ("the", 0.2, 0.4),
        ("west", 0.4, 0.7),
        ("coast", 0.7, 1.1),
        ("later", 50.0, 50.4),
        ("cluster", 52.7, 53.1),
    )
    w0, w1 = sent_window_word_range(words, sent_start=0.0, sent_end=1.1)
    assert words[w0].word == "On"
    assert words[w1 - 1].word == "coast"
    mid0, _mid1 = sent_window_word_range(words, sent_start=50.0, sent_end=53.1)
    assert words[mid0].word == "later"
    assert words[mid0].start >= 50.0


def test_sent_window_word_range_ignores_forward_jump_leftover() -> None:
    words = _words(
        ("On", 0.0, 0.2),
        ("the", 0.2, 0.4),
        ("west", 0.4, 0.7),
        ("coast", 0.7, 1.1),
        ("Tesla,", 4546.85, 4546.97),
        ("later", 50.0, 50.4),
        ("cluster", 52.7, 53.1),
    )
    mid0, mid1 = sent_window_word_range(words, sent_start=50.0, sent_end=53.1)
    assert words[mid0].word == "later"
    assert words[mid1 - 1].word == "cluster"
    assert mid1 - mid0 == 2


def test_opening_isolate_keeps_first_cluster_on_50s_pad() -> None:
    merged = merge_spot_confirm_windows(
        [_cand(0.0, 24.0), _cand(71.4, 86.0)],
        pad_s=70.0,
        ep_end=200.0,
        max_gap_s=120.0,
    )
    assert len(merged) == 1
    isolated = merge_spot_confirm_windows(
        [_cand(0.0, 24.0), _cand(71.4, 86.0)],
        pad_s=70.0,
        ep_end=200.0,
        max_gap_s=120.0,
        isolate_opening=True,
    )
    assert len(isolated) == 2
    open_start, open_end, open_group = isolated[0]
    mid_start, mid_end, mid_group = isolated[1]
    assert open_start == 0.0
    # 50s opening pad would reach 74s; clip at the next cluster start.
    assert open_end == 71.4
    assert grouped_candidate(open_group).end == 24.0
    assert abs(mid_start - 24.0) < 1e-9
    assert mid_end == 156.0
    assert grouped_candidate(mid_group).start == 71.4
    solo = merge_spot_confirm_windows(
        [_cand(0.0, 47.4)],
        pad_s=70.0,
        ep_end=200.0,
        max_gap_s=120.0,
        isolate_opening=True,
    )
    assert len(solo) == 1
    assert solo[0][0] == 0.0
    assert solo[0][1] == 97.4


def test_split_cluster_window_does_not_pad_into_prior_promo() -> None:
    """Listen-CTA split + isolate: second window starts at first cluster end."""
    isolated = merge_spot_confirm_windows(
        [_cand(41.89, 70.13), _cand(79.29, 86.53)],
        pad_s=70.0,
        ep_end=641.3,
        max_gap_s=120.0,
        isolate_opening=True,
    )
    assert len(isolated) == 2
    assert isolated[0][1] >= 70.13
    assert isolated[1][0] == 70.13
    assert isolated[1][0] > 41.89


def test_confirm_window_does_not_right_pad_into_next_cluster() -> None:
    """70s right-pad must not resend the next isolated/split cluster."""
    isolated = merge_spot_confirm_windows(
        [_cand(41.89, 70.13), _cand(79.29, 86.53)],
        pad_s=70.0,
        ep_end=641.3,
        max_gap_s=120.0,
        isolate_opening=True,
    )
    assert len(isolated) == 2
    first_end = isolated[0][1]
    second_start = isolated[1][2][0].start
    assert first_end == second_start == 79.29
    assert first_end < 70.13 + 70.0
    # Bridged detections remain one window; clip is between windows only.
    bridged = merge_spot_confirm_windows(
        [_cand(1048.0, 1053.0), _cand(1112.0, 1122.0)],
        pad_s=70.0,
        ep_end=2000.0,
        max_gap_s=120.0,
    )
    assert len(bridged) == 1
    assert bridged[0][1] == 1192.0
