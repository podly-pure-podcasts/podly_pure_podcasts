from __future__ import annotations

from podcast_processor.word_transcripts import (
    ALIGNED_BACKEND,
    group_segment_rows,
    payload_from_aligned_words,
    payload_is_aligned,
)


def test_group_segment_rows_packs_until_max_span() -> None:
    rows = [(0.0, 5.0, "a"), (5.0, 10.0, "b"), (20.0, 25.0, "c")]
    groups = group_segment_rows(rows, max_span_s=28.0)
    assert groups == [rows]


def test_group_segment_rows_splits_when_span_exceeds() -> None:
    rows = [(0.0, 5.0, "a"), (5.0, 20.0, "b"), (20.0, 40.0, "c")]
    groups = group_segment_rows(rows, max_span_s=28.0)
    assert groups == [[rows[0], rows[1]], [rows[2]]]


def test_group_segment_rows_isolates_overlong_segment() -> None:
    rows = [(0.0, 4.0, "a"), (4.0, 40.0, "long"), (41.0, 45.0, "c")]
    groups = group_segment_rows(rows, max_span_s=28.0)
    assert groups == [[rows[0]], [rows[1]], [rows[2]]]


def test_lexicon_lock_keeps_segment_tokens_when_dtw_glues() -> None:
    from podcast_processor.word_transcripts import lock_words_to_segment_lexicon

    rows = [(864.6, 865.8, "Let's join us again tomorrow.")]
    dtw = [
        {"word": "Let'sjoin", "start": 864.61, "end": 864.95},
        {"word": "us", "start": 864.95, "end": 865.03},
        {"word": "again", "start": 865.03, "end": 865.17},
        {"word": "tomorrow.", "start": 865.17, "end": 865.39},
    ]
    locked = lock_words_to_segment_lexicon(dtw, rows)
    labels = [row["word"].lower() for row in locked]
    assert "join" in labels
    assert "letsjoin" not in {item.replace("'", "") for item in labels}


def test_lexicon_mismatch_times_on_dtw_span_not_full_segment() -> None:
    from podcast_processor.word_transcripts import lexicon_words_for_segment

    dtw = [
        {"word": "Thisepisode", "start": 475.2, "end": 476.0},
        {"word": "Locker.", "start": 477.1, "end": 477.8},
    ]
    locked = lexicon_words_for_segment(
        465.84,
        478.0,
        "This episode is sponsored by Threat Locker.",
        dtw_words=dtw,
    )
    assert locked[0]["word"] == "This"
    assert locked[0]["start"] >= 474.5
    assert locked[-1]["end"] <= 478.05


def test_reanchor_packs_leading_bed_stretch() -> None:
    from podcast_processor.quote_anchor import WordTiming
    from podcast_processor.word_transcripts import reanchor_words_to_speech

    ident = [
        WordTiming("This", 457.44, 457.75),
        WordTiming("is", 457.75, 458.31),
        WordTiming("Darknet", 458.31, 458.73),
        WordTiming("Diaries.", 458.73, 459.27),
    ]
    # Linear interpol across 465.84-478 music+speech.
    stretched = [
        WordTiming("This", 465.84, 467.58),
        WordTiming("episode", 467.58, 469.31),
        WordTiming("is", 469.31, 471.05),
        WordTiming("sponsored", 471.05, 472.79),
        WordTiming("by", 472.79, 474.53),
        WordTiming("Threat", 474.53, 476.26),
        WordTiming("Locker.", 476.26, 478.00),
    ]
    segs = [
        (457.44, 465.68, "This is Darknet Diaries."),
        (465.84, 478.00, "This episode is sponsored by Threat Locker."),
    ]
    out = reanchor_words_to_speech(ident + stretched, segs, gaps=[])
    locker = [w for w in out if w.start >= 464]
    assert locker[0].word == "This"
    assert locker[0].start >= 474.0
    assert locker[-1].end <= 478.05


def test_reanchor_restores_intra_segment_silence_pause() -> None:
    from podcast_processor.quote_anchor import WordTiming
    from podcast_processor.word_transcripts import reanchor_words_to_speech

    words = [
        WordTiming("Plus,", 1208.36, 1209.15),
        WordTiming("we", 1209.15, 1209.94),
        WordTiming("go", 1209.94, 1210.73),
        WordTiming("back", 1210.73, 1211.52),
        WordTiming("to", 1211.52, 1212.31),
        WordTiming("our", 1212.31, 1213.10),
        WordTiming("former", 1213.10, 1213.90),
        WordTiming("chief", 1213.90, 1214.69),
        WordTiming("actuary", 1214.69, 1215.48),
        WordTiming("for", 1215.48, 1216.27),
        WordTiming("a", 1216.27, 1217.06),
        WordTiming("reality", 1217.06, 1217.85),
        WordTiming("check.", 1217.85, 1218.64),
        WordTiming("This", 1218.64, 1218.99),
    ]
    segs = [
        (
            1208.36,
            1218.64,
            "Plus we go back to our former chief actuary for a reality check.",
        ),
        (1218.64, 1223.52, "This election season"),
    ]
    gaps = [(1215.38, 1217.08)]
    out = reanchor_words_to_speech(words, segs, gaps)
    plus = [w for w in out if w.word != "This"]
    nxt = next(w for w in out if w.word == "This")
    assert plus[-1].word == "check."
    assert plus[-1].end <= 1215.45
    assert nxt.start - plus[-1].end >= 0.8


def test_reanchor_keeps_overlapping_sentences_contiguous() -> None:
    """Indicator 1433: duplicate alignment must not interleave the teaser."""
    from podcast_processor.quote_anchor import WordTiming, match_quote_tokens
    from podcast_processor.word_transcripts import reanchor_words_to_speech

    words = [
        WordTiming("The", 579.15, 579.63),
        WordTiming("President's", 579.63, 580.03),
        WordTiming("supply", 580.03, 580.43),
        WordTiming("side", 580.43, 580.83),
        WordTiming("inflation.", 582.83, 583.23),
        WordTiming("Three", 579.77, 580.25),
        WordTiming("years", 580.25, 580.57),
        WordTiming("after", 580.57, 580.87),
        WordTiming("October", 580.87, 581.39),
        WordTiming("7th", 581.39, 582.05),
        WordTiming("and", 582.05, 582.09),
        WordTiming("the", 582.09, 582.23),
    ]
    segs = [
        (575.4, 579.4, "The President's supply side inflation."),
        (579.4, 583.4, "Three years after October 7th and the"),
    ]
    # Force overlap assignment like live: words already overlap 579-583.
    out = reanchor_words_to_speech(words, segs, gaps=[])
    joined = " ".join(w.word for w in out)
    assert "Three years after October" in joined
    assert match_quote_tokens(out, "Three years after October 7th and the") is not None


def test_payload_is_aligned_rejects_decoder_word_timestamps() -> None:
    bad = {"word_timestamps": True, "words": [{"word": "hi", "start": 0, "end": 0.2}]}
    good = payload_from_aligned_words(
        [{"word": "Wise", "start": 404.4, "end": 404.8}],
        [(404.36, 419.36, "This message comes from Wise")],
        model_name="base",
        audio_path="x.mp3",
        align_s=1.2,
    )
    assert payload_is_aligned(bad) is False
    assert payload_is_aligned(good) is True
    assert good["backend"] == ALIGNED_BACKEND
    assert good["word_timestamps"] is False


def test_fill_whisper_segment_holes_keeps_speech(tmp_path) -> None:
    import numpy as np

    from podcast_processor.word_transcripts import (
        fill_whisper_segment_holes,
    )

    class FakeModel:
        def transcribe(self, _clip, **_kwargs):
            return {
                "segments": [
                    {
                        "start": 2.3,
                        "end": 5.5,
                        "text": " This message comes from Wise.",
                        "avg_logprob": -0.24,
                        "no_speech_prob": 0.16,
                    }
                ]
            }

    segs = [
        {"start": 53.9, "end": 57.0, "text": " We'll tell you why after the break."},
        {"start": 83.9, "end": 90.6, "text": " Listen to the swing state"},
    ]
    out = fill_whisper_segment_holes(
        tmp_path / "x.mp3",
        segs,
        FakeModel(),
        load_audio=lambda _path: np.zeros(16000 * 90, dtype=np.float32),
        sample_rate=16000,
    )
    texts = [str(row.get("text") or "").strip() for row in out]
    assert "This message comes from Wise." in texts
    wise = next(row for row in out if "Wise" in str(row.get("text") or ""))
    assert 57.0 <= float(wise["start"]) < 70.0
    assert float(wise["end"]) <= 83.9


def test_fill_whisper_segment_holes_drops_low_logprob_bed(tmp_path) -> None:
    import numpy as np

    from podcast_processor.word_transcripts import (
        fill_whisper_segment_holes,
    )

    class FakeModel:
        def transcribe(self, _clip, **_kwargs):
            return {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 14.0,
                        "text": " Being the youngest man in the world",
                        "avg_logprob": -4.63,
                        "no_speech_prob": 0.38,
                    }
                ]
            }

    segs = [
        {"start": 864.6, "end": 865.4, "text": " tomorrow."},
        {"start": 887.0, "end": 893.0, "text": " This week on Sources and Methods"},
    ]
    out = fill_whisper_segment_holes(
        tmp_path / "x.mp3",
        segs,
        FakeModel(),
        load_audio=lambda _path: np.zeros(16000 * 40, dtype=np.float32),
        sample_rate=16000,
    )
    assert len(out) == 2
    assert all("youngest" not in str(row.get("text") or "") for row in out)


def test_fill_whisper_segment_holes_drops_sparse_thank_you_bed(tmp_path) -> None:
    import numpy as np

    from podcast_processor.word_transcripts import (
        fill_whisper_segment_holes,
    )

    class FakeModel:
        def transcribe(self, _clip, **_kwargs):
            return {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 12.0,
                        "text": " Thank you.",
                        "avg_logprob": -0.92,
                        "no_speech_prob": 0.18,
                    }
                ]
            }

    segs = [
        {"start": 3320.0, "end": 3329.4, "text": " Thanks for listening."},
        {"start": 3341.4, "end": 3350.0, "text": " This message comes from Wise"},
    ]
    out = fill_whisper_segment_holes(
        tmp_path / "x.mp3",
        segs,
        FakeModel(),
        load_audio=lambda _path: np.zeros(16000 * 40, dtype=np.float32),
        sample_rate=16000,
    )
    assert len(out) == 2
    assert all("Thank you" not in str(row.get("text") or "") for row in out)


def test_word_cache_path_for_audio_appends_suffix(tmp_path) -> None:
    from podcast_processor.word_transcripts import word_cache_path_for_audio

    audio = tmp_path / "episode.mp3"
    assert word_cache_path_for_audio(audio) == tmp_path / "episode.mp3.words.json"
