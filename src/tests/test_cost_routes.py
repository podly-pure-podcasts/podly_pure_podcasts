from datetime import datetime

import pytest

from app.extensions import db
from app.models import (
    Feed,
    Identification,
    ModelCall,
    Post,
    ProcessingJob,
    TranscriptSegment,
)
from app.routes.cost_routes import costs_bp


@pytest.fixture
def costs_app(app, monkeypatch):
    app.testing = True
    app.register_blueprint(costs_bp)
    monkeypatch.setattr(
        "app.routes.cost_routes.read_combined",
        lambda: {"app": {"cost_rate_per_hour": 0.04}},
    )
    return app


def _completed_post(duration=3600, completed_at=None, status="completed"):
    feed = Feed(title="Example", rss_url="https://example.com/feed.xml")
    db.session.add(feed)
    db.session.flush()
    post = Post(
        feed_id=feed.id,
        guid="episode",
        title="Episode",
        download_url="https://example.com/episode.mp3",
        duration=duration,
    )
    db.session.add(post)
    db.session.add(
        ProcessingJob(
            post_guid=post.guid,
            status=status,
            completed_at=completed_at or datetime(2026, 2, 15),
        )
    )
    db.session.commit()
    return post


def _summary(app):
    response = app.test_client().get("/api/admin/costs?year=2026&month=2")
    assert response.status_code == 200
    return response.get_json()


def test_empty_month_has_zero_audio_hours(costs_app):
    payload = _summary(costs_app)
    assert payload["total_audio_hours"] == 0.0
    assert payload["total_cost"] == 0.0


def test_audio_hours_counts_reprocessed_episodes_once(costs_app):
    post = _completed_post()
    db.session.add(
        ProcessingJob(
            post_guid=post.guid,
            status="completed",
            completed_at=datetime(2026, 2, 20),
        )
    )
    db.session.commit()
    payload = _summary(costs_app)
    assert payload["total_audio_hours"] == 1.0
    assert payload["feeds"][0]["episodes_this_month"] == 1
    assert payload["total_cost"] == 0.04


@pytest.mark.parametrize("duration", [None, 0, -60])
def test_missing_or_nonpositive_duration_contributes_zero_hours(costs_app, duration):
    _completed_post(duration=duration)
    assert _summary(costs_app)["total_audio_hours"] == 0.0


def _add_transcript(post, end_time, ad_confidence=None):
    segments = [
        TranscriptSegment(
            post_id=post.id, sequence_num=0, start_time=0, end_time=600, text="An ad"
        ),
        TranscriptSegment(
            post_id=post.id,
            sequence_num=1,
            start_time=600,
            end_time=end_time,
            text="Content",
        ),
    ]
    db.session.add_all(segments)
    db.session.flush()
    if ad_confidence is not None:
        call = ModelCall(
            post_id=post.id,
            first_segment_sequence_num=0,
            last_segment_sequence_num=1,
            model_name="model",
            prompt="Classify",
            status="success",
        )
        db.session.add(call)
        db.session.flush()
        db.session.add(
            Identification(
                transcript_segment_id=segments[0].id,
                model_call_id=call.id,
                label="ad",
                confidence=ad_confidence,
            )
        )
    db.session.commit()


def test_audio_hours_use_transcript_length_when_ads_were_cut(costs_app):
    _add_transcript(_completed_post(duration=3000), end_time=3600, ad_confidence=0.95)
    payload = _summary(costs_app)
    assert payload["total_audio_hours"] == 1.0
    assert payload["total_cost"] == 0.04


def test_uncut_low_confidence_ads_are_not_added_back(costs_app):
    _add_transcript(_completed_post(duration=3600), end_time=3600, ad_confidence=0.2)
    payload = _summary(costs_app)
    assert payload["total_audio_hours"] == 1.0
    assert payload["total_cost"] == 0.04


def test_cleared_duration_falls_back_to_transcript_length(costs_app):
    _add_transcript(_completed_post(duration=None), end_time=3600)
    assert _summary(costs_app)["total_audio_hours"] == 1.0


@pytest.mark.parametrize(
    ("completed_at", "status", "expected_hours"),
    [
        (datetime(2026, 1, 31, 23, 59, 59), "completed", 0.0),
        (datetime(2026, 2, 1), "completed", 1.0),
        (datetime(2026, 2, 28, 23, 59, 59), "completed", 1.0),
        (datetime(2026, 3, 1), "completed", 0.0),
        (datetime(2026, 2, 15), "failed", 0.0),
    ],
)
def test_audio_hours_uses_selected_month_and_completed_jobs(
    costs_app, completed_at, status, expected_hours
):
    _completed_post(completed_at=completed_at, status=status)
    assert _summary(costs_app)["total_audio_hours"] == expected_hours
