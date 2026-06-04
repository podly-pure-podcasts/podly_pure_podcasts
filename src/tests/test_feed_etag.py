"""Tests for ETag / Last-Modified / 304 short-circuit on feed routes.

These cover PR 2 of the feed performance audit. The aim is for podcast
readers polling an unchanged feed to receive a fast 304 response that
skips the upstream fetch and the XML rebuild entirely.
"""

from __future__ import annotations

import datetime as dt
from unittest import mock

from werkzeug.http import http_date

from app.extensions import db
from app.feeds import generate_feed_xml
from app.models import Feed, Post
from app.routes import feed_routes
from app.routes.feed_routes import feed_bp
from app.writer.actions.feeds import refresh_feed_action


def _make_feed_with_post(rss_url: str = "https://example.com/feed.xml") -> int:
    feed = Feed(title="Etag Feed", rss_url=rss_url)
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


def test_feed_has_default_last_changed_at(app):
    with app.app_context():
        feed = Feed(title="Feed A", rss_url="https://example.com/a.xml")
        db.session.add(feed)
        db.session.commit()
        db.session.refresh(feed)
        assert feed.last_changed_at is not None
        assert isinstance(feed.last_changed_at, dt.datetime)


def test_refresh_feed_action_bumps_last_changed_at_on_new_post(app):
    with app.app_context():
        feed = Feed(title="Feed B", rss_url="https://example.com/b.xml")
        db.session.add(feed)
        db.session.commit()
        original_changed = feed.last_changed_at
        # ensure the bump produces a strictly later timestamp
        feed.last_changed_at = original_changed - dt.timedelta(hours=1)
        db.session.commit()
        old_changed = feed.last_changed_at

        refresh_feed_action(
            {
                "feed_id": feed.id,
                "new_posts": [
                    {
                        "guid": "new-guid",
                        "title": "New Ep",
                        "description": "",
                        "download_url": "https://example.com/b/new.mp3",
                        "release_date": "2026-04-01T12:00:00+00:00",
                        "duration": 60,
                        "image_url": None,
                        "whitelisted": False,
                        "feed_id": feed.id,
                    }
                ],
            }
        )
        db.session.commit()
        db.session.refresh(feed)
        assert feed.last_changed_at is not None
        assert feed.last_changed_at > old_changed


def test_refresh_feed_action_bumps_last_changed_at_on_existing_post_update(app):
    with app.app_context():
        feed = Feed(title="Feed C", rss_url="https://example.com/c.xml")
        db.session.add(feed)
        db.session.commit()
        post = Post(
            feed_id=feed.id,
            guid="g-c",
            download_url="https://example.com/c/ep.mp3",
            title="Old title",
        )
        db.session.add(post)
        db.session.commit()
        feed.last_changed_at = feed.last_changed_at - dt.timedelta(hours=1)
        db.session.commit()
        old_changed = feed.last_changed_at

        refresh_feed_action(
            {
                "feed_id": feed.id,
                "existing_post_updates": [
                    {"post_id": post.id, "title": "Newer title"},
                ],
            }
        )
        db.session.commit()
        db.session.refresh(feed)
        assert feed.last_changed_at > old_changed


def test_refresh_feed_action_does_not_bump_when_nothing_changes(app):
    with app.app_context():
        feed = Feed(title="Feed D", rss_url="https://example.com/d.xml")
        db.session.add(feed)
        db.session.commit()
        old_changed = feed.last_changed_at

        refresh_feed_action({"feed_id": feed.id})
        db.session.commit()
        db.session.refresh(feed)
        assert feed.last_changed_at == old_changed


def test_generate_feed_xml_uses_feed_last_changed_at(app):
    """`lastBuildDate` must come from `Feed.last_changed_at`, not now()."""
    with app.app_context():
        feed_id = _make_feed_with_post()
        feed = db.session.get(Feed, feed_id)
        fixed = dt.datetime(2025, 6, 15, 10, 30, 0)
        feed.last_changed_at = fixed
        db.session.commit()

        with mock.patch("app.feeds._get_base_url", return_value="http://test"):
            xml_bytes = generate_feed_xml(feed)
        xml = xml_bytes.decode("utf-8") if isinstance(xml_bytes, bytes) else xml_bytes
        # RSS pubDate / lastBuildDate format: e.g., "Sun, 15 Jun 2025 10:30:00 +0000"
        assert "15 Jun 2025 10:30:00" in xml


def _register_feed_routes(app) -> None:
    if "feed" not in app.blueprints:
        app.register_blueprint(feed_bp)


def _reset_kickoff_state() -> None:
    with feed_routes._BACKGROUND_REFRESH_LOCK:
        feed_routes._BACKGROUND_REFRESH_LAST_KICKOFF.clear()


def test_get_feed_emits_etag_and_last_modified_headers(app):
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        resp = client.get(f"/feed/{feed_id}")

    assert resp.status_code == 200
    assert resp.headers.get("ETag")
    assert resp.headers.get("Last-Modified")


def test_get_feed_returns_304_when_etag_matches(app):
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh") as mock_spawn,
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        first = client.get(f"/feed/{feed_id}")
        etag = first.headers["ETag"]

        second = client.get(f"/feed/{feed_id}", headers={"If-None-Match": etag})

    assert second.status_code == 304
    # the body of a 304 must be empty
    assert second.get_data(as_text=True) == ""
    # ETag header is required on a 304 per RFC 9110
    assert second.headers.get("ETag") == etag
    # the second call must NOT have kicked off a refresh — that's the entire point.
    assert mock_spawn.call_count == 1  # only the first call scheduled refresh


def test_get_feed_skips_refresh_and_xml_when_etag_matches(app):
    """The 304 path is the latency win: refresh and XML build must be skipped."""
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()
        feed = db.session.get(Feed, feed_id)
        # We need a stable ETag value to check on the FIRST request,
        # so seed last_changed_at to a known value.
        feed.last_changed_at = dt.datetime(2026, 1, 1, 0, 0, 0)
        db.session.commit()

    client = app.test_client()
    # First, get the canonical ETag the route would produce.
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        bootstrap = client.get(f"/feed/{feed_id}")
    etag = bootstrap.headers["ETag"]

    # Now make a fresh request with If-None-Match. Both refresh and XML should
    # be untouched — that's the latency win.
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh") as mock_spawn,
        mock.patch("app.routes.feed_routes.generate_feed_xml") as mock_gen,
    ):
        resp = client.get(f"/feed/{feed_id}", headers={"If-None-Match": etag})

    assert resp.status_code == 304
    mock_spawn.assert_not_called()
    mock_gen.assert_not_called()


def test_get_feed_returns_200_when_etag_does_not_match(app):
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        resp = client.get(
            f"/feed/{feed_id}", headers={"If-None-Match": '"obviously-stale"'}
        )

    assert resp.status_code == 200
    assert resp.data == b"<rss/>"


def test_get_feed_returns_304_when_if_modified_since_recent(app):
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()
        feed = db.session.get(Feed, feed_id)
        feed.last_changed_at = dt.datetime(2026, 1, 1, 0, 0, 0)
        db.session.commit()

    client = app.test_client()
    # Client claims it last fetched 1 hour AFTER our last_changed_at — so 304.
    later = dt.datetime(2026, 1, 1, 1, 0, 0, tzinfo=dt.UTC)
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh") as mock_spawn,
        mock.patch("app.routes.feed_routes.generate_feed_xml") as mock_gen,
    ):
        resp = client.get(
            f"/feed/{feed_id}", headers={"If-Modified-Since": http_date(later)}
        )

    assert resp.status_code == 304
    mock_spawn.assert_not_called()
    mock_gen.assert_not_called()


def test_get_feed_etag_changes_when_last_changed_at_changes(app):
    app.testing = True
    _register_feed_routes(app)
    _reset_kickoff_state()

    with app.app_context():
        feed_id = _make_feed_with_post()
        feed = db.session.get(Feed, feed_id)
        feed.last_changed_at = dt.datetime(2026, 1, 1, 0, 0, 0)
        db.session.commit()
    # In real deployments the writer runs in a separate process so the request
    # session never sees a stale identity-map entry. The pytest fixture wraps
    # everything in a single app context (and therefore a single shared
    # session), so we expire it explicitly to mirror that behavior.
    db.session.expire_all()

    client = app.test_client()
    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        first = client.get(f"/feed/{feed_id}")
    first_etag = first.headers["ETag"]

    with app.app_context():
        feed = db.session.get(Feed, feed_id)
        feed.last_changed_at = dt.datetime(2026, 1, 2, 0, 0, 0)
        db.session.commit()
    db.session.expire_all()

    with (
        mock.patch("app.routes.feed_routes._spawn_async_refresh"),
        mock.patch("app.routes.feed_routes.generate_feed_xml", return_value=b"<rss/>"),
    ):
        second = client.get(f"/feed/{feed_id}")

    assert second.headers["ETag"] != first_etag


def test_get_user_aggregate_feed_emits_etag(app):
    app.testing = True
    _register_feed_routes(app)

    with app.app_context():
        app.config["REQUIRE_AUTH"] = False
        _make_feed_with_post("https://example.com/agg-1.xml")
        _make_feed_with_post("https://example.com/agg-2.xml")

    client = app.test_client()
    with mock.patch(
        "app.routes.feed_routes.generate_aggregate_feed_xml", return_value=b"<rss/>"
    ):
        resp = client.get("/feed/user/0")

    assert resp.status_code == 200
    assert resp.headers.get("ETag")
    assert resp.headers.get("Last-Modified")


def test_get_user_aggregate_feed_returns_304_when_etag_matches(app):
    app.testing = True
    _register_feed_routes(app)

    with app.app_context():
        app.config["REQUIRE_AUTH"] = False
        _make_feed_with_post("https://example.com/agg-3.xml")
        _make_feed_with_post("https://example.com/agg-4.xml")

    client = app.test_client()
    with mock.patch(
        "app.routes.feed_routes.generate_aggregate_feed_xml", return_value=b"<rss/>"
    ) as mock_gen:
        first = client.get("/feed/user/0")
        etag = first.headers["ETag"]
        second = client.get("/feed/user/0", headers={"If-None-Match": etag})

    assert second.status_code == 304
    # XML must not be regenerated on the 304 path
    assert mock_gen.call_count == 1
