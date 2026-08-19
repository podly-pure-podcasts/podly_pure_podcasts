from types import SimpleNamespace
from unittest import mock

from flask import Blueprint

from app.extensions import db
from app.models import Feed
from app.routes.feed_routes import feed_bp


def _make_client(app):
    app.testing = True
    app.register_blueprint(feed_bp)
    # add_feed redirects to main.index — stub it so url_for resolves.
    if "main" not in app.blueprints:
        main_bp = Blueprint("main", __name__)

        @main_bp.route("/", endpoint="index")
        def _index():
            return "ok"

        app.register_blueprint(main_bp)
    return app.test_client()


def _make_feed(rss_url="http://example.com/feed.rss", language=None):
    feed = Feed(title="Test Feed", rss_url=rss_url, language=language)
    db.session.add(feed)
    db.session.commit()
    return feed


def test_update_feed_settings_language_valid(app):
    with app.app_context():
        feed = _make_feed()
        feed_id = feed.id
        client = _make_client(app)

        def _writer_update_side_effect(
            model_name: str, model_id: int, updates: dict, wait: bool = True
        ):
            assert model_name == "Feed"
            assert model_id == feed_id
            assert updates == {"language": "de"}
            Feed.query.filter_by(id=model_id).update(updates)
            db.session.commit()
            return SimpleNamespace(success=True)

        with mock.patch("app.routes.feed_routes.writer_client") as mock_writer:
            mock_writer.update.side_effect = _writer_update_side_effect

            response = client.patch(
                f"/api/feeds/{feed_id}/settings",
                json={"language": "de"},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["language"] == "de"


def test_update_feed_settings_language_null_clears(app):
    with app.app_context():
        feed = _make_feed(rss_url="http://example.com/feed2.rss", language="de")
        feed_id = feed.id
        client = _make_client(app)

        def _writer_update_side_effect(
            model_name: str, model_id: int, updates: dict, wait: bool = True
        ):
            assert model_name == "Feed"
            assert model_id == feed_id
            assert updates == {"language": None}
            Feed.query.filter_by(id=model_id).update(updates)
            db.session.commit()
            return SimpleNamespace(success=True)

        with mock.patch("app.routes.feed_routes.writer_client") as mock_writer:
            mock_writer.update.side_effect = _writer_update_side_effect

            response = client.patch(
                f"/api/feeds/{feed_id}/settings",
                json={"language": None},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["language"] is None


def test_update_feed_settings_language_invalid_returns_400(app):
    with app.app_context():
        feed = _make_feed(rss_url="http://example.com/feed3.rss")
        client = _make_client(app)

        response = client.patch(
            f"/api/feeds/{feed.id}/settings",
            json={"language": "klingon"},
        )

        assert response.status_code == 400
        assert "language must be one of" in response.get_json()["error"]


def test_update_feed_settings_language_non_string_returns_400(app):
    with app.app_context():
        feed = _make_feed(rss_url="http://example.com/feed5.rss")
        client = _make_client(app)

        response = client.patch(
            f"/api/feeds/{feed.id}/settings",
            json={"language": ["en", "de"]},
        )

        assert response.status_code == 400
        assert "language must be one of" in response.get_json()["error"]


def test_add_feed_with_language_on_new_feed(app):
    """Adding a brand-new feed with a language persists it via the writer."""
    with app.app_context():
        client = _make_client(app)
        url = "http://example.com/add-lang.rss"

        def fake_add_or_refresh(_url, language=None):
            assert language == "de"
            feed = Feed(title="New Feed", rss_url=_url, language=language)
            db.session.add(feed)
            db.session.commit()
            return feed

        with (
            mock.patch(
                "app.routes.feed_routes.add_or_refresh_feed",
                side_effect=fake_add_or_refresh,
            ),
            mock.patch("app.routes.feed_routes.Thread"),
            mock.patch("app.routes.feed_routes.writer_client") as mock_writer,
        ):

            def writer_side_effect(action, params, wait=False):
                assert action != "update_feed_settings"
                return SimpleNamespace(success=True)

            mock_writer.action.side_effect = writer_side_effect

            response = client.post(
                "/feed",
                data={"url": url, "language": "de"},
                follow_redirects=False,
            )

        assert response.status_code in (200, 302), response.data
        feed = Feed.query.filter_by(rss_url=url).first()
        assert feed is not None
        assert feed.language == "de"
        update_calls = [
            c
            for c in mock_writer.action.call_args_list
            if c.args[0] == "update_feed_settings"
        ]
        assert len(update_calls) == 0


def test_add_feed_existing_language_preserved_in_writer(app):
    """Re-adding an existing feed always calls the writer with only_if_unset=True;
    the writer itself preserves any prior language. This serializes the
    race-vs-retry semantics inside the writer rather than the request session.
    """
    with app.app_context():
        client = _make_client(app)
        existing = _make_feed(
            rss_url="http://example.com/add-preserve.rss", language="fr"
        )

        with (
            mock.patch(
                "app.routes.feed_routes.add_or_refresh_feed", return_value=existing
            ),
            mock.patch("app.routes.feed_routes.Thread"),
            mock.patch("app.routes.feed_routes.writer_client") as mock_route_writer,
            mock.patch("app.feeds.writer_client") as mock_feed_writer,
        ):
            mock_route_writer.action.return_value = SimpleNamespace(success=True)
            mock_feed_writer.action.return_value = SimpleNamespace(success=True)
            response = client.post(
                "/feed",
                data={"url": "http://example.com/add-preserve.rss", "language": "de"},
                follow_redirects=False,
            )

        assert response.status_code in (200, 302), response.data
        update_calls = [
            c
            for c in mock_feed_writer.action.call_args_list
            if c.args[0] == "update_feed_settings"
        ]
        assert len(update_calls) == 1
        assert update_calls[0].args[1].get("only_if_unset") is True


def test_add_feed_sets_existing_feed_language_via_writer(app):
    """Re-adding an existing feed persists the requested language through the writer."""
    with app.app_context():
        client = _make_client(app)
        existing = _make_feed(rss_url="http://example.com/order.rss")

        def feed_writer_side_effect(action, params, wait=False):
            Feed.query.filter_by(id=params["feed_id"]).update(
                {"language": params["language"]}
            )
            db.session.commit()
            return SimpleNamespace(success=True, data={"language": params["language"]})

        with (
            mock.patch(
                "app.routes.feed_routes.add_or_refresh_feed", return_value=existing
            ),
            mock.patch("app.routes.feed_routes.Thread"),
            mock.patch("app.feeds.writer_client") as mock_feed_writer,
        ):
            mock_feed_writer.action.side_effect = feed_writer_side_effect

            response = client.post(
                "/feed",
                data={"url": "http://example.com/order.rss", "language": "de"},
                follow_redirects=False,
            )

        assert response.status_code in (200, 302), response.data
        update_calls = [
            c
            for c in mock_feed_writer.action.call_args_list
            if c.args[0] == "update_feed_settings"
        ]
        assert len(update_calls) == 1
        assert update_calls[0].args[1]["language"] == "de"
        db.session.refresh(existing)
        assert existing.language == "de"


def test_update_feed_settings_action_only_if_unset(app):
    """The writer action skips the language write when only_if_unset=True
    and the feed already has a language."""
    from app.writer.actions.feeds import update_feed_settings_action

    with app.app_context():
        feed = _make_feed(rss_url="http://example.com/only-if-unset.rss", language="fr")
        result = update_feed_settings_action(
            {"feed_id": feed.id, "language": "de", "only_if_unset": True}
        )
        db.session.refresh(feed)
        assert feed.language == "fr"
        assert result["language"] == "fr"

        result2 = update_feed_settings_action({"feed_id": feed.id, "language": "de"})
        db.session.refresh(feed)
        assert feed.language == "de"
        assert result2["language"] == "de"


def test_update_feed_settings_action_only_if_unset_writes_when_null(app):
    """only_if_unset still writes when the prior value was null."""
    from app.writer.actions.feeds import update_feed_settings_action

    with app.app_context():
        feed = _make_feed(rss_url="http://example.com/only-if-null.rss")
        assert feed.language is None
        update_feed_settings_action(
            {"feed_id": feed.id, "language": "de", "only_if_unset": True}
        )
        db.session.refresh(feed)
        assert feed.language == "de"


def test_add_feed_writer_failure_returns_500_before_enqueue(app):
    """If an explicit language write fails, the request fails before jobs enqueue."""
    with app.app_context():
        client = _make_client(app)
        url = "http://example.com/add-writer-fail.rss"
        created: dict[str, Feed] = {}

        def fake_add_or_refresh(_url, language=None):
            feed = Feed(title="WF", rss_url=_url)
            db.session.add(feed)
            db.session.commit()
            created["feed"] = feed
            return feed

        with (
            mock.patch(
                "app.routes.feed_routes.add_or_refresh_feed",
                side_effect=fake_add_or_refresh,
            ),
            mock.patch("app.routes.feed_routes.Thread") as mock_thread,
            mock.patch("app.routes.feed_routes.writer_client") as mock_route_writer,
            mock.patch("app.feeds.writer_client") as mock_feed_writer,
        ):
            mock_route_writer.action.return_value = SimpleNamespace(success=True)
            mock_feed_writer.action.return_value = SimpleNamespace(
                success=False, error="boom"
            )
            response = client.post(
                "/feed",
                data={"url": url, "language": "de"},
                follow_redirects=False,
            )

        assert response.status_code == 500, response.data
        feed = Feed.query.filter_by(rss_url=url).first()
        assert feed is not None
        assert feed.language is None
        mock_thread.assert_not_called()
        assert [c.args[0] for c in mock_feed_writer.action.call_args_list] == [
            "update_feed_settings"
        ]
        mock_route_writer.action.assert_not_called()


def test_add_feed_invalid_language_returns_400(app):
    with app.app_context():
        client = _make_client(app)

        response = client.post(
            "/feed",
            data={"url": "http://example.com/add-bad.rss", "language": "klingon"},
        )

        assert response.status_code == 400
        assert b"language must be one of" in response.data


def test_add_feed_no_language_leaves_null(app):
    with app.app_context():
        client = _make_client(app)
        existing = _make_feed(rss_url="http://example.com/add-nolang.rss")

        with (
            mock.patch(
                "app.routes.feed_routes.add_or_refresh_feed", return_value=existing
            ),
            mock.patch("app.routes.feed_routes.Thread"),
        ):
            response = client.post(
                "/feed",
                data={"url": "http://example.com/add-nolang.rss"},
                follow_redirects=False,
            )

        assert response.status_code in (200, 302)
        db.session.refresh(existing)
        assert existing.language is None


def test_update_feed_settings_no_fields_returns_400(app):
    with app.app_context():
        feed = _make_feed(rss_url="http://example.com/feed4.rss")
        client = _make_client(app)

        response = client.patch(
            f"/api/feeds/{feed.id}/settings",
            json={},
        )

        assert response.status_code == 400
        assert "No settings provided" in response.get_json()["error"]
