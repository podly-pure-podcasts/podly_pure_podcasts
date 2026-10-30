from __future__ import annotations

from pathlib import Path

from podcast_processor.boundary_snap import (
    SilenceGap,
    interpolate_word_times,
    parse_silencedetect,
    refine_cuts,
    snap_cuts_to_silence,
    snap_time_to_silence,
    trim_cut_to_word_extents,
)


def test_interpolate_word_times_covers_segment() -> None:
    words = interpolate_word_times(10.0, 12.0, "hello there friend")
    assert [w.word for w in words] == ["hello", "there", "friend"]
    assert words[0].start == 10.0
    assert words[-1].end == 12.0
    assert abs(words[1].start - (10.0 + 2.0 / 3.0)) < 1e-9


def test_trim_cut_to_word_extents_is_noop_for_segment_aligned_cut() -> None:
    segments = [(0.0, 5.0, "ad words here"), (5.0, 8.0, "more ad")]
    assert trim_cut_to_word_extents((0.0, 8.0), segments) == (0.0, 8.0)


def test_trim_cut_to_word_extents_snaps_mid_segment_to_words() -> None:
    segments = [(10.0, 14.0, "one two three four")]
    start, end = trim_cut_to_word_extents((9.5, 14.4), segments)
    assert start == 10.0
    assert end == 14.0


def test_parse_silencedetect_pairs() -> None:
    text = (
        "silence_start: 1.25\n"
        "silence_end: 1.80 | silence_duration: 0.55\n"
        "silence_start: 8.00\n"
        "silence_end: 8.40\n"
    )
    gaps = parse_silencedetect(text, time_offset=100.0)
    assert gaps == [
        SilenceGap(start=101.25, end=101.80),
        SilenceGap(start=108.00, end=108.40),
    ]


def test_snap_start_to_nearest_silence_end() -> None:
    gaps = [SilenceGap(start=8.0, end=8.4), SilenceGap(start=12.0, end=12.3)]
    assert snap_time_to_silence(8.7, gaps, radius=2.5, kind="start") == 8.4
    assert snap_time_to_silence(8.7, gaps, radius=0.2, kind="start") == 8.7
    # Inward start may only move later.
    assert (
        snap_time_to_silence(8.7, gaps, radius=2.5, kind="start", prefer="inward")
        == 8.7
    )
    assert (
        snap_time_to_silence(8.0, gaps, radius=2.5, kind="start", prefer="inward")
        == 8.4
    )
    later = [SilenceGap(start=8.8, end=9.0)]
    assert snap_time_to_silence(8.7, later, radius=2.5, kind="start") == 9.0
    assert (
        snap_time_to_silence(
            8.7, later, radius=2.5, kind="start", prefer="earlier_start"
        )
        == 8.7
    )


def test_snap_end_to_nearest_silence_start() -> None:
    gaps = [SilenceGap(start=20.2, end=20.6), SilenceGap(start=24.0, end=24.5)]
    assert snap_time_to_silence(20.0, gaps, radius=2.5, kind="end") == 20.2
    assert (
        snap_time_to_silence(20.5, gaps, radius=2.5, kind="end", prefer="inward")
        == 20.2
    )
    assert (
        snap_time_to_silence(20.0, gaps, radius=2.5, kind="end", prefer="inward")
        == 20.0
    )


def test_snap_cuts_keeps_window_if_collapse() -> None:
    gaps = [SilenceGap(start=5.1, end=5.2), SilenceGap(start=5.3, end=5.4)]
    cuts = snap_cuts_to_silence([(5.0, 5.5)], gaps, radius=2.5, min_length=2.0)
    assert cuts == [(5.0, 5.5)]


def test_snap_cuts_moves_both_edges() -> None:
    gaps = [
        SilenceGap(start=9.6, end=10.1),
        SilenceGap(start=19.8, end=20.4),
    ]
    cuts = snap_cuts_to_silence([(10.4, 20.0)], gaps, radius=2.5, min_length=1.0)
    assert cuts == [(10.1, 19.8)]


def test_refine_cuts_word_only_without_audio() -> None:
    refined = refine_cuts(
        [(9.7, 20.4)],
        audio_path=None,
        segments=[(10.0, 20.0, "ad copy here today")],
    )
    assert refined == [(10.0, 20.0)]


def test_refine_cuts_missing_audio_file_keeps_cuts() -> None:
    refined = refine_cuts(
        [(3.0, 12.0)],
        audio_path=Path("/no/such/file.mp3"),
        radius=2.5,
    )
    assert refined == [(3.0, 12.0)]
