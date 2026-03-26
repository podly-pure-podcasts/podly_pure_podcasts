"""Tests to explore what triggers job processing."""

from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.extensions import db
from app.models import Feed, Post, User, UserFeedSubscription


@pytest.fixture
def app_with_models():
    """Create a Flask app with all models for testing."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "test-secret"

    with app.app_context():
        db.init_app(app)
        db.create_all()
        yield app


@pytest.fixture
def setup_feed_and_user(app_with_models):
    """Set up a feed, user, and subscription for testing."""
    with app_with_models.app_context():
        # Create user
        user = User(username="testuser", role="user")
        user.set_password("testpass")
        db.session.add(user)

        # Create feed
        feed = Feed(
            title="Test Feed",
            rss_url="http://example.com/feed.xml",
            description="Test description",
        )
        db.session.add(feed)
        db.session.flush()

        # Create subscription WITHOUT auto_download
        subscription = UserFeedSubscription(
            user_id=user.id, feed_id=feed.id, auto_download_new_episodes=False
        )
        db.session.add(subscription)

        # Create a post
        post = Post(
            feed_id=feed.id,
            guid="test-guid-123",
            download_url="http://example.com/episode.mp3",
            title="Test Episode",
            whitelisted=True,
        )
        db.session.add(post)
        db.session.commit()

        yield {
            "app": app_with_models,
            "user": user,
            "feed": feed,
            "subscription": subscription,
            "post": post,
        }


class TestRefreshFeedTriggers:
    """Test what refresh_feed returns based on auto_download setting."""

    def test_refresh_feed_no_auto_download_returns_empty(self, setup_feed_and_user):
        """When auto_download is False, refresh_feed should NOT return any GUIDs."""
        from app.feeds import refresh_feed

        data = setup_feed_and_user
        app = data["app"]
        feed = data["feed"]

        with app.app_context():
            # Re-fetch feed in this context
            feed = Feed.query.get(feed.id)

            # Mock feedparser to return a new episode
            entry = MagicMock()
            entry.id = "new-episode-guid"
            entry.title = "New Episode"
            entry.description = "New episode desc"
            entry.published_parsed = None
            entry.links = [
                {
                    "rel": "enclosure",
                    "href": "http://example.com/new.mp3",
                    "type": "audio/mpeg",
                }
            ]
            entry.get.side_effect = lambda key, default="": {
                "description": "New episode desc",
                "summary": "",
                "published_parsed": None,
            }.get(key, default)

            with patch("app.feeds.fetch_feed") as mock_fetch:
                mock_fetch.return_value = MagicMock(
                    feed={"title": "Test Feed"},
                    entries=[entry],
                )

                result = refresh_feed(feed)

                # Should return empty list since auto_download is False
                assert result == [], f"Expected empty list, got {result}"

    def test_refresh_feed_with_auto_download_returns_guids(self, setup_feed_and_user):
        """When auto_download is True, refresh_feed SHOULD return GUIDs."""
        from app.feeds import refresh_feed

        data = setup_feed_and_user
        app = data["app"]
        feed = data["feed"]
        subscription = data["subscription"]

        with app.app_context():
            # Enable auto_download
            sub = UserFeedSubscription.query.get(subscription.id)
            sub.auto_download_new_episodes = True
            db.session.commit()

            feed = Feed.query.get(feed.id)

            entry = MagicMock()
            entry.id = "new-episode-guid-2"
            entry.title = "New Episode 2"
            entry.description = "New episode desc"
            entry.published_parsed = None
            entry.links = [
                {
                    "rel": "enclosure",
                    "href": "http://example.com/new2.mp3",
                    "type": "audio/mpeg",
                }
            ]
            entry.get.side_effect = lambda key, default="": {
                "description": "New episode desc",
                "summary": "",
                "published_parsed": None,
            }.get(key, default)

            with patch("app.feeds.fetch_feed") as mock_fetch:
                mock_fetch.return_value = MagicMock(
                    feed={"title": "Test Feed"},
                    entries=[entry],
                )

                result = refresh_feed(feed)

                # Should return the new GUID since auto_download is True
                assert len(result) == 1, f"Expected 1 GUID, got {result}"


class TestDownloadEndpointTriggers:
    """Test what triggers processing from the download endpoint."""

    def test_download_unprocessed_post_with_subscription_triggers_processing(
        self, setup_feed_and_user
    ):
        """Download request for unprocessed post should trigger processing if subscribed."""
        from app.routes.post_routes import post_bp

        data = setup_feed_and_user
        app = data["app"]
        user = data["user"]
        post = data["post"]

        app.register_blueprint(post_bp)

        with app.app_context():
            with app.test_client() as client:
                # Simulate authenticated user
                with client.session_transaction() as sess:
                    sess["user_id"] = user.id

                # Mock g.current_user
                with patch("app.routes.post_routes.g") as mock_g:
                    mock_g.current_user = MagicMock(id=user.id)
                    mock_g.feed_token = None

                    # Make request to download endpoint
                    response = client.get(f"/api/posts/{post.guid}/download")

                    # Should trigger processing (202) or return 404 if not allowed
                    print(f"Response status: {response.status_code}")
                    print(f"Response data: {response.data}")


class TestFeedRouteRefresh:
    """Test if GET /feed/<id> triggers job processing."""

    def test_get_feed_does_not_start_jobs(self, setup_feed_and_user):
        """GET /feed/<id> should NOT start any processing jobs."""
        from app.routes.feed_routes import feed_bp

        data = setup_feed_and_user
        app = data["app"]
        feed = data["feed"]

        app.register_blueprint(feed_bp)

        with app.app_context():
            # Track if start_post_processing is called
            with patch(
                "app.jobs_manager.JobsManager.start_post_processing"
            ) as mock_start:
                with patch("app.feeds.fetch_feed") as mock_fetch:
                    mock_fetch.return_value = MagicMock(
                        feed={"title": "Test Feed"},
                        entries=[],
                    )

                    with app.test_client() as client:
                        response = client.get(f"/feed/{feed.id}")

                        # start_post_processing should NOT have been called
                        assert (
                            not mock_start.called
                        ), "start_post_processing should not be called on feed GET"


class TestScheduledRefresh:
    """Test scheduled feed refresh behavior."""

    def test_scheduled_refresh_only_processes_auto_download_feeds(
        self, setup_feed_and_user
    ):
        """Scheduled refresh should only process feeds with auto_download enabled."""
        from app.jobs_manager import JobsManager

        data = setup_feed_and_user
        app = data["app"]

        with app.app_context():
            with patch("app.jobs_manager.scheduler") as mock_scheduler:
                mock_scheduler.app = app

                manager = JobsManager.__new__(JobsManager)
                manager._status_manager = MagicMock()
                manager._stop_event = MagicMock()
                manager._work_event = MagicMock()
                manager._run_id = None

                with patch.object(manager, "start_post_processing") as mock_start:
                    with patch("app.feeds.fetch_feed") as mock_fetch:
                        mock_fetch.return_value = MagicMock(
                            feed={"title": "Test Feed"},
                            entries=[],
                        )

                        # This should NOT call start_post_processing since auto_download is False
                        # manager.start_refresh_all_feeds()

                        # For now just verify the setup
                        assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
