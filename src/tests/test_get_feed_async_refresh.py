"""Tests for PR 3: `GET /feed/<id>` no longer blocks on `refresh_feed`.

The route used to issue a synchronous upstream RSS fetch on every reader
poll, which made feed-fetch latency upstream-bounded. PR 3 drops that
synchronous call and instead kicks off a debounced refresh on a background
thread (when not already kicked off recently). The scheduled
`refresh_all_feeds` job remains the primary freshness source.
"""

from __future__ import annotations

import datetime as dt
from unittest import mock

from app.extensions import db
from app.models import Feed, Post
from app.routes import feed_routes
from app.routes.feed_routes import feed_bp


def _make_feed_with_post(rss_url: str = "https://example.com/feed.xml") -> int:
    feed = Feed(title="PR3 Feed", rss_url=rss_url)
    db.session.add(feed)
    db.session.commit()

    post = Post(
        feed_id=feed.id,
        guid=f"post-guid-{feed.id}",
        download_url=f"{rss_url}/ep1.mp3",
        title="Episode 1",
        release_date=dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.UTC),
    )
    db.session.add(post)
    db.session.commit()
    return feed.id


def _register_feed_routes(app) -> None:
    if "feed" not in app.blueprints:
        app.register_blueprint(feed_bp)


def _reset_kickoff_state() -> None:
    with feed_routes._BACKGROUND_REFRESH_LOCK:
        feed_routes._BACKGROUND_REFRESH_LAST_KICKOFF.clear()


def test_get_feed_does_not_call_refresh_feed_synchronously(app):
    """The hot path on the request thread must not block on upstream fetch."""
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes.refresh_feed") as mock_refresh,
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
    ):
        resp = client.get(f"/feed/{feed_id}")

    assert resp.status_code == 200
    mock_refresh.assert_not_called()


def test_get_feed_kicks_off_async_refresh(app):
    """First poll for a feed should schedule a background refresh."""
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
        mock.patch("app.routes.feed_routes._spawn_async_refresh") as mock_spawn,
    ):
        resp = client.get(f"/feed/{feed_id}")

    assert resp.status_code == 200
    mock_spawn.assert_called_once()
    args, _ = mock_spawn.call_args
    # second positional arg is the feed id
    assert args[1] == feed_id


def test_get_feed_debounces_repeated_polls(app):
    """Quick repeat polls within the cooldown must not re-spawn refreshes."""
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
        mock.patch("app.routes.feed_routes._spawn_async_refresh") as mock_spawn,
    ):
        client.get(f"/feed/{feed_id}")
        client.get(f"/feed/{feed_id}")
        client.get(f"/feed/{feed_id}")

    assert mock_spawn.call_count == 1


def test_get_feed_kickoff_resumes_after_cooldown(app):
    """After the cooldown elapses, a fresh poll should kick off again."""
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    base = 1000.0
    times = iter([base, base + 1.0, base + 1000.0])

    with (
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
        mock.patch("app.routes.feed_routes._spawn_async_refresh") as mock_spawn,
        mock.patch(
            "app.routes.feed_routes.time.monotonic", side_effect=lambda: next(times)
        ),
    ):
        client.get(f"/feed/{feed_id}")  # base: kickoff
        client.get(f"/feed/{feed_id}")  # base + 1s: debounced
        client.get(f"/feed/{feed_id}")  # base + 1000s: kickoff again

    assert mock_spawn.call_count == 2


def test_get_feed_kickoff_independent_per_feed(app):
    """Different feeds have independent cooldown windows."""
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_a = _make_feed_with_post("https://example.com/a.xml")
        feed_b = _make_feed_with_post("https://example.com/b.xml")

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
        mock.patch("app.routes.feed_routes._spawn_async_refresh") as mock_spawn,
    ):
        client.get(f"/feed/{feed_a}")
        client.get(f"/feed/{feed_b}")
        client.get(f"/feed/{feed_a}")  # within cooldown — debounced

    assert mock_spawn.call_count == 2
    feed_ids = [call.args[1] for call in mock_spawn.call_args_list]
    assert feed_ids == [feed_a, feed_b]


def test_get_feed_returns_xml_when_kickoff_skipped(app):
    """Even when the refresh is debounced, the response must still serve XML."""
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    with (
        mock.patch(
            "app.routes.feed_routes.generate_feed_xml",
            return_value=b"<rss/>cached</rss/>",
        ),
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
    ):
        first = client.get(f"/feed/{feed_id}")
        second = client.get(f"/feed/{feed_id}")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.data == b"<rss/>cached</rss/>"
