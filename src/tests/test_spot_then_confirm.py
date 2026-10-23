"""Spot-then-confirm: one LLM call per spotted window, edge extend."""

from __future__ import annotations

import json

from flask import Flask

from app.extensions import db
from app.models import Feed, Post, TranscriptSegment
from podcast_processor.quote_anchor import WordTiming
from podcast_processor.quote_anchor_classifier import QuoteAnchorClassifier
from shared.config import TestWhisperConfig as WhisperTestConfig
from shared.local_writer import force_local_writer
from shared.test_utils import create_standard_test_config


def _spot_config(*, pad: float = 50.0):
    config = create_standard_test_config()
    return config.model_copy(update={"whisper": WhisperTestConfig()}), pad


def _seed(
    title: str, rows: list[tuple[float, float, str]]
) -> tuple[Post, list[TranscriptSegment]]:
    feed = Feed(title="Test Feed", rss_url="http://example.com/rss.xml")
    db.session.add(feed)
    db.session.commit()
    post = Post(
        feed_id=feed.id,
        title=title,
        guid="spot-guid",
        download_url="http://example.com/audio.mp3",
        unprocessed_audio_path="missing.mp3",
    )
    db.session.add(post)
    db.session.commit()
    segments = [
        TranscriptSegment(
            post_id=post.id,
            sequence_num=i,
            start_time=a,
            end_time=b,
            text=text,
        )
        for i, (a, b, text) in enumerate(rows)
    ]
    db.session.add_all(segments)
    db.session.commit()
    return post, segments


def _words_from_rows(rows: list[tuple[float, float, str]]) -> list[WordTiming]:
    words: list[WordTiming] = []
    for start, end, text in rows:
        parts = text.split()
        if not parts:
            continue
        dt = max(0.05, (end - start) / len(parts))
        t = start
        for part in parts:
            words.append(WordTiming(word=part, start=t, end=min(end, t + dt)))
            t += dt
    return words


def test_one_llm_call_per_candidate_not_whole_episode(app: Flask) -> None:
    force_local_writer()
    with app.app_context():
        rows = [
            (0.0, 8.0, "Good morning everyone welcome back to the show."),
            (
                8.0,
                16.0,
                "This episode is sponsored by NetSuite. Get the guide at netsuite.com slash darknet.",
            ),
            (16.0, 24.0, "And we are back with the story from last week."),
        ]
        post, segments = _seed("Darknet", rows)
        calls: list[str] = []

        def complete(_system: str, user: str) -> str:
            calls.append(user)
            return json.dumps(
                {
                    "ads": [
                        {
                            "start_quote": "This episode is sponsored by NetSuite",
                            "end_quote": "guide at netsuite.com slash darknet",
                            "content_type": "promotional_external",
                            "confidence": 0.95,
                        }
                    ]
                }
            )

        config, pad = _spot_config(pad=8.0)
        classifier = QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=pad,
        )
        cuts = classifier.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert len(classifier.last_candidates) >= 1
        assert classifier.last_llm_calls == len(calls)
        assert (
            classifier.last_llm_calls
            == len(classifier.last_candidates) + classifier.last_extends
        )
        assert cuts
        assert any("CANDIDATE" in user for user in calls)


def test_confirm_not_ad_returns_no_cut(app: Flask) -> None:
    force_local_writer()
    with app.app_context():
        rows = [
            (0.0, 6.0, "This episode is sponsored by NetSuite in a case study."),
            (6.0, 12.0, "The engineers at the company built a database."),
        ]
        post, segments = _seed("Tech", rows)

        def complete(_system: str, _user: str) -> str:
            return '{"ads":[]}'

        config, pad = _spot_config(pad=4.0)
        classifier = QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=pad,
        )
        cuts = classifier.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert classifier.last_llm_calls >= 1
        assert cuts == []


def test_padding_edge_extends_once(app: Flask) -> None:
    force_local_writer()
    with app.app_context():
        rows = [
            (
                0.0,
                10.0,
                "Brought to you by Honey. Visit joinhoney.com slash pod for the app.",
            ),
            (
                10.0,
                80.0,
                "The hosts talk about the news of the day in great detail here for a long while.",
            ),
            (
                80.0,
                90.0,
                "Ordinary conversation continues without any sponsor mention at all.",
            ),
            (90.0, 100.0, "Alpha bravo charlie delta echo foxtrot continue the story."),
            (
                100.0,
                110.0,
                "This episode is sponsored by NetSuite. Visit netsuite.com slash demo.",
            ),
            (
                110.0,
                120.0,
                "Back to the interview with more of the conversation today.",
            ),
        ]
        post, segments = _seed("Extend", rows)
        calls = {"n": 0}

        def complete(_system: str, user: str) -> str:
            if "joinhoney.com" in user:
                return json.dumps(
                    {
                        "ads": [
                            {
                                "start_quote": "Brought to you by Honey",
                                "end_quote": "joinhoney.com slash pod for the app",
                                "content_type": "promotional_external",
                                "confidence": 0.95,
                            }
                        ]
                    }
                )
            calls["n"] += 1
            if calls["n"] == 1:
                # Quote the padding edge so the matcher sits on the window start.
                return json.dumps(
                    {
                        "ads": [
                            {
                                "start_quote": "Alpha bravo charlie delta echo",
                                "end_quote": "Visit netsuite.com slash demo",
                                "content_type": "promotional_external",
                                "confidence": 0.95,
                            }
                        ]
                    }
                )
            return json.dumps(
                {
                    "ads": [
                        {
                            "start_quote": "This episode is sponsored by NetSuite",
                            "end_quote": "Visit netsuite.com slash demo",
                            "content_type": "promotional_external",
                            "confidence": 0.95,
                        }
                    ]
                }
            )

        config, pad = _spot_config(pad=9.0)
        classifier = QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=pad,
        )
        classifier.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert classifier.last_extends == 1
        assert classifier.last_llm_calls >= 2


def test_extend_union_keeps_first_confirm(app: Flask) -> None:
    force_local_writer()
    with app.app_context():
        rows = [
            (
                0.0,
                10.0,
                "Brought to you by Honey. Visit joinhoney.com slash pod for the app.",
            ),
            (
                10.0,
                80.0,
                "The hosts talk about the news of the day in great detail here for a long while.",
            ),
            (
                80.0,
                90.0,
                "Ordinary conversation continues without any sponsor mention at all.",
            ),
            (90.0, 100.0, "Alpha bravo charlie delta echo foxtrot continue the story."),
            (
                100.0,
                110.0,
                "This episode is sponsored by NetSuite. Visit netsuite.com slash demo.",
            ),
            (
                110.0,
                120.0,
                "Back to the interview with more of the conversation today.",
            ),
        ]
        post, segments = _seed("Union", rows)
        calls = {"n": 0}

        def complete(_system: str, user: str) -> str:
            if "joinhoney.com" in user:
                return json.dumps(
                    {
                        "ads": [
                            {
                                "start_quote": "Brought to you by Honey",
                                "end_quote": "joinhoney.com slash pod for the app",
                                "content_type": "promotional_external",
                                "confidence": 0.95,
                            }
                        ]
                    }
                )
            calls["n"] += 1
            if calls["n"] == 1:
                return json.dumps(
                    {
                        "ads": [
                            {
                                "start_quote": "Alpha bravo charlie delta echo",
                                "end_quote": "Visit netsuite.com slash demo",
                                "content_type": "promotional_external",
                                "confidence": 0.95,
                            }
                        ]
                    }
                )
            return json.dumps(
                {
                    "ads": [
                        {
                            "start_quote": "This episode is sponsored by NetSuite",
                            "end_quote": "Visit netsuite.com slash demo",
                            "content_type": "promotional_external",
                            "confidence": 0.95,
                        }
                    ]
                }
            )

        config, pad = _spot_config(pad=9.0)
        classifier = QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=pad,
        )
        classifier.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert classifier.last_extends == 1
        assert classifier.last_matches
        midroll = [item for item in classifier.last_matches if item.start > 50.0]
        assert midroll
        # Union: first confirm's earlier start survives the second reply.
        assert min(item.start for item in midroll) < 99.0


def test_opening_isolate_keeps_lone_cluster_on_50s_pad(app: Flask) -> None:
    """A single midroll cluster uses the 50s opening pad, not 70s."""
    force_local_writer()
    with app.app_context():
        rows = [
            (0.0, 12.0, "UNIQUEOPENINGTOKEN hello this is the cold open of the show."),
            (
                12.0,
                55.0,
                "Ordinary host chatter continues for a while without sponsors.",
            ),
            (55.0, 70.0, "Still chatting about the news of the day in some detail."),
            (
                70.0,
                82.0,
                "This episode is sponsored by NetSuite. Visit netsuite.com slash demo.",
            ),
            (82.0, 95.0, "And we are back with more of the interview today."),
        ]
        post, segments = _seed("Pad", rows)
        prompts: list[str] = []

        def complete(_system: str, user: str) -> str:
            prompts.append(user)
            return json.dumps(
                {
                    "ads": [
                        {
                            "start_quote": "This episode is sponsored by NetSuite",
                            "end_quote": "Visit netsuite.com slash demo",
                            "content_type": "promotional_external",
                            "confidence": 0.95,
                        }
                    ]
                }
            )

        config, _ = _spot_config()
        QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=70.0,
        ).classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert prompts
        assert "UNIQUEOPENINGTOKEN" not in prompts[0]
        assert "sponsored by NetSuite" in prompts[0]


def _cadillac_rows() -> list[tuple[float, float, str]]:
    # First segment must overlap win_start (cluster~53.5 - 50s pad ≈ 3.5)
    # so Gemini sees t=0 while word_from=win_start-1 still clips "On".
    return [
        (
            0.0,
            6.0,
            "On the west coast the spirit of adventure meets the art of refinement.",
        ),
        (6.0, 22.0, "Visit CadillacCanada.ca for the Cadillac Definition of Luxury."),
        (
            22.0,
            52.0,
            "Ordinary host chatter continues without any sponsor mention here.",
        ),
        (
            52.0,
            58.0,
            "Check it out wherever you get your podcasts this week on sister.",
        ),
        (58.0, 70.0, "Listen to the episode right now everywhere you subscribe."),
        (70.0, 90.0, "And we are back with more of the interview today."),
    ]


def _cadillac_reply() -> str:
    return json.dumps(
        {
            "ads": [
                {
                    "start_quote": "On the west coast the spirit of",
                    "end_quote": "for the Cadillac Definition of Luxury",
                    "content_type": "promotional_external",
                    "confidence": 0.95,
                }
            ]
        }
    )


def test_sent_window_search_recovers_clipped_opening(app: Flask) -> None:
    force_local_writer()
    with app.app_context():
        rows = _cadillac_rows()
        post, segments = _seed("Cadillac", rows)
        prompts: list[str] = []

        def complete(_system: str, user: str) -> str:
            prompts.append(user)
            return _cadillac_reply()

        config, _ = _spot_config(pad=50.0)
        clf = QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=50.0,
        )
        clf.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert clf.last_matches
        assert min(item.start for item in clf.last_matches) < 1.0
        assert any(item.method == "word" for item in clf.last_matches)
        assert clf.last_extends in {0, 1}
        assert "On the west coast" in prompts[0]


def test_prompt_word_bounds_unmatched_quote_stays_cluster_fallback(
    app: Flask,
) -> None:
    force_local_writer()
    with app.app_context():
        rows = _cadillac_rows()
        post, segments = _seed("Fallback", rows)

        def complete(_system: str, _user: str) -> str:
            return json.dumps(
                {
                    "ads": [
                        {
                            "start_quote": "This quote does not appear anywhere",
                            "end_quote": "nor does this ending phrase either",
                            "content_type": "promotional_external",
                            "confidence": 0.95,
                        }
                    ]
                }
            )

        on, _ = _spot_config(pad=50.0)
        clf = QuoteAnchorClassifier(
            config=on,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=50.0,
        )
        clf.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert clf.last_candidates
        cand = min(clf.last_candidates, key=lambda c: c.start)
        assert clf.last_matches
        match = clf.last_matches[0]
        assert match.method == "chunk_fallback"
        assert match.start == max(0.0, cand.start - 2.0)
        assert match.end <= cand.end + 2.0 + 1e-6


def test_prompt_word_bounds_still_extends_when_left_transcript_exists(
    app: Flask,
) -> None:
    force_local_writer()
    with app.app_context():
        rows = [
            (
                0.0,
                10.0,
                "Brought to you by Honey. Visit joinhoney.com slash pod for the app.",
            ),
            (
                10.0,
                80.0,
                "The hosts talk about the news of the day in great detail here for a long while.",
            ),
            (
                80.0,
                90.0,
                "Ordinary conversation continues without any sponsor mention at all.",
            ),
            (90.0, 100.0, "Alpha bravo charlie delta echo foxtrot continue the story."),
            (
                100.0,
                110.0,
                "This episode is sponsored by NetSuite. Visit netsuite.com slash demo.",
            ),
            (
                110.0,
                120.0,
                "Back to the interview with more of the conversation today.",
            ),
        ]
        post, segments = _seed("ExtendBounds", rows)
        calls = {"n": 0}

        def complete(_system: str, user: str) -> str:
            if "joinhoney.com" in user:
                return json.dumps(
                    {
                        "ads": [
                            {
                                "start_quote": "Brought to you by Honey",
                                "end_quote": "joinhoney.com slash pod for the app",
                                "content_type": "promotional_external",
                                "confidence": 0.95,
                            }
                        ]
                    }
                )
            calls["n"] += 1
            if calls["n"] == 1:
                return json.dumps(
                    {
                        "ads": [
                            {
                                "start_quote": "Alpha bravo charlie delta echo",
                                "end_quote": "Visit netsuite.com slash demo",
                                "content_type": "promotional_external",
                                "confidence": 0.95,
                            }
                        ]
                    }
                )
            return json.dumps(
                {
                    "ads": [
                        {
                            "start_quote": "This episode is sponsored by NetSuite",
                            "end_quote": "Visit netsuite.com slash demo",
                            "content_type": "promotional_external",
                            "confidence": 0.95,
                        }
                    ]
                }
            )

        config, pad = _spot_config(pad=9.0)
        classifier = QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=pad,
        )
        classifier.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert classifier.last_extends == 1
        assert classifier.last_llm_calls >= 2


def test_prompt_word_bounds_later_window_does_not_match_opening_prefix(
    app: Flask,
) -> None:
    """Midroll confirms keep win_start-1 so a quoted cold-open cannot
    first-best a later cluster back to t=0."""
    force_local_writer()
    with app.app_context():
        rows = [
            (0.0, 20.0, "On the west coast the spirit of adventure meets refinement."),
            (
                20.0,
                40.0,
                "Visit CadillacCanada.ca for the Cadillac Definition of Luxury.",
            ),
            (
                40.0,
                70.0,
                "Ordinary host chatter continues without any sponsor mention here.",
            ),
            (
                200.0,
                212.0,
                "This episode is sponsored by NetSuite. Visit netsuite.com slash demo.",
            ),
            (212.0, 230.0, "And we are back with more of the interview today."),
        ]
        post, segments = _seed("LaterPrefix", rows)

        def complete(_system: str, user: str) -> str:
            if "sponsored by NetSuite" in user or "netsuite.com" in user:
                return json.dumps(
                    {
                        "ads": [
                            {
                                "start_quote": "On the west coast the spirit of",
                                "end_quote": "Visit netsuite.com slash demo",
                                "content_type": "promotional_external",
                                "confidence": 0.95,
                            }
                        ]
                    }
                )
            return '{"ads":[]}'

        config, pad = _spot_config(pad=50.0)
        classifier = QuoteAnchorClassifier(
            config=config,
            db_session=db.session,
            complete_fn=complete,
            spot_pad_s=pad,
        )
        classifier.classify(
            transcript_segments=segments,
            post=post,
            words=_words_from_rows(rows),
        )
        assert classifier.last_candidates
        later = max(classifier.last_candidates, key=lambda c: c.start)
        assert later.start >= 190.0
        later_matches = [
            item for item in classifier.last_matches if item.start >= 140.0
        ]
        assert later_matches
        assert min(item.start for item in later_matches) >= 140.0
