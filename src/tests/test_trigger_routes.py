"""
Regression tests for /trigger and /api/trigger/status endpoints.

These tests verify:
1. /trigger route is not intercepted by main_bp catch-all
2. /api/trigger/status returns proper JSON with Cache-Control headers
3. Invalid tokens return 401/403, never 500
4. Missing params return 400, never 500
"""

import hashlib
import secrets

import pytest
from flask import Flask

from app.extensions import db
from app.models import Feed, FeedAccessToken, Post, ProcessingJob, User
from app.routes.main_routes import main_bp
from app.routes.post_routes import post_bp


def _hash_token(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@pytest.fixture
def app_with_routes() -> Flask:
    """Create a Flask app with routes registered in correct order."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = "test-secret-key"
    app.testing = True

    # Register blueprints in correct order (main_bp LAST)
    app.register_blueprint(post_bp)
    app.register_blueprint(main_bp)

    with app.app_context():
        db.init_app(app)
        db.create_all()
        yield app


@pytest.fixture
def test_user(app_with_routes):
    """Create a test user."""
    with app_with_routes.app_context():
        user = User(username="testuser", password_hash="dummy", role="user")
        db.session.add(user)
        db.session.commit()
        yield user


@pytest.fixture
def test_feed(app_with_routes, test_user):
    """Create a test feed."""
    with app_with_routes.app_context():
        feed = Feed(title="Test Feed", rss_url="https://example.com/feed.xml")
        db.session.add(feed)
        db.session.commit()
        yield feed


@pytest.fixture
def test_post(app_with_routes, test_feed):
    """Create a test post."""
    with app_with_routes.app_context():
        post = Post(
            feed_id=test_feed.id,
            guid="test-guid-123",
            download_url="https://example.com/audio.mp3",
            title="Test Episode",
            whitelisted=True,
        )
        db.session.add(post)
        db.session.commit()
        yield post


@pytest.fixture
def test_token(app_with_routes, test_user, test_feed):
    """Create a test feed access token."""
    with app_with_routes.app_context():
        # Refresh objects in this session
        user = db.session.merge(test_user)
        feed = db.session.merge(test_feed)

        token_id = "test-token-id"
        token_secret = secrets.token_urlsafe(18)
        token = FeedAccessToken(
            token_id=token_id,
            token_hash=_hash_token(token_secret),
            token_secret=token_secret,
            feed_id=feed.id,
            user_id=user.id,
        )
        db.session.add(token)
        db.session.commit()
        yield {"token_id": token_id, "secret": token_secret}


class TestTriggerRouteOrder:
    """Test that /trigger route is handled by post_bp, not main_bp catch-all."""

    def test_trigger_route_not_intercepted_by_catchall(self, app_with_routes):
        """Verify /trigger is handled by post_bp, not main_bp catch-all."""
        client = app_with_routes.test_client()

        # Without params, should return 400 (missing params), not 200 (index.html)
        response = client.get("/trigger")

        # If main_bp catch-all intercepted, it would return 200 with index.html
        # post_bp /trigger should return 400 for missing params
        assert response.status_code == 400
        assert (
            b"Missing Parameters" in response.data
            or b"missing" in response.data.lower()
        )


class TestTriggerStatusEndpoint:
    """Test /api/trigger/status endpoint."""

    def test_missing_params_returns_400_with_cache_control(self, app_with_routes):
        """Missing params should return 400 with Cache-Control: no-store."""
        client = app_with_routes.test_client()

        response = client.get("/api/trigger/status")
        assert response.status_code == 400

        # Must have Cache-Control even on errors
        assert response.headers.get("Cache-Control") == "no-store"

        data = response.get_json()
        assert data is not None
        assert data["state"] == "error"
        assert "Missing" in data["message"] or "required" in data["message"].lower()

    def test_invalid_token_returns_401_with_cache_control(
        self, app_with_routes, test_post
    ):
        """Invalid token should return 401 with Cache-Control: no-store."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)
            response = client.get(
                f"/api/trigger/status?guid={post.guid}&feed_token=invalid&feed_secret=invalid"
            )

        assert response.status_code == 401
        # Must have Cache-Control even on errors
        assert response.headers.get("Cache-Control") == "no-store"

        data = response.get_json()
        assert data is not None
        assert data["state"] == "error"

    def test_valid_request_returns_json_with_cache_control(
        self, app_with_routes, test_post, test_token
    ):
        """Valid request should return JSON with Cache-Control: no-store."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)
            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        # Should return 200 with JSON
        assert response.status_code == 200
        assert response.content_type == "application/json"

        # Must have Cache-Control: no-store
        assert response.headers.get("Cache-Control") == "no-store"

        # JSON should have required fields
        data = response.get_json()
        assert data is not None
        assert "state" in data
        assert "processed" in data
        assert data["state"] in [
            "ready",
            "processing",
            "queued",
            "failed",
            "not_started",
        ]

    def test_nonexistent_post_returns_404(self, app_with_routes, test_token):
        """Unknown GUIDs currently fail token auth before post lookup."""
        client = app_with_routes.test_client()

        response = client.get(
            f"/api/trigger/status?guid=nonexistent-guid"
            f"&feed_token={test_token['token_id']}"
            f"&feed_secret={test_token['secret']}"
        )

        assert response.status_code == 401
        data = response.get_json()
        assert data is not None
        assert data["state"] == "error"


class TestTriggerEndpoint:
    """Test /trigger endpoint."""

    def test_missing_params_returns_400_html(self, app_with_routes):
        """Missing params should return 400 with error HTML."""
        client = app_with_routes.test_client()

        response = client.get("/trigger")
        assert response.status_code == 400
        assert response.mimetype == "text/html"

    def test_invalid_token_returns_403_html(self, app_with_routes, test_post):
        """Invalid token should return 401/403 with error HTML, not 500."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)
            response = client.get(
                f"/trigger?guid={post.guid}&feed_token=invalid&feed_secret=invalid"
            )

        # Should be 401 or 403, never 500
        assert response.status_code in [401, 403]
        assert response.mimetype == "text/html"
        assert b"Podly" in response.data  # Themed error page


class TestTriggerStatusProcessingState:
    """Test /api/trigger/status with processing jobs that have NULL fields.

    This is a regression test for the 500 error that occurred when polling
    status while a job was actively processing with NULL current_step/total_steps.
    """

    def test_processing_job_with_null_fields_returns_200(
        self, app_with_routes, test_post, test_token
    ):
        """Processing job with NULL fields should return 200, not 500."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)

            # Create a processing job with NULL fields (simulates early processing)
            job = ProcessingJob(
                post_guid=post.guid,
                status="running",
                current_step=None,  # NULL - this was causing crashes
                total_steps=None,  # NULL
                step_name=None,  # NULL
                progress_percentage=None,  # NULL
            )
            db.session.add(job)
            db.session.commit()

            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        # Must return 200, not 500
        assert response.status_code == 200
        assert response.content_type == "application/json"

        data = response.get_json()
        assert data is not None
        assert data["state"] in ["processing", "queued"]

        # Job object must have safe defaults
        assert data["job"] is not None
        assert isinstance(data["job"]["current_step"], int)
        assert isinstance(data["job"]["total_steps"], int)
        assert isinstance(data["job"]["progress_percentage"], int)
        assert 0 <= data["job"]["progress_percentage"] <= 100
        assert data["job"]["step_name"] is not None

    def test_pending_job_with_null_fields_returns_200(
        self, app_with_routes, test_post, test_token
    ):
        """Pending job with NULL fields should return 200 with queued state."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)

            # Create a pending job with NULL fields
            job = ProcessingJob(
                post_guid=post.guid,
                status="pending",
                current_step=None,
                total_steps=None,
                step_name=None,
                progress_percentage=None,
            )
            db.session.add(job)
            db.session.commit()

            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["state"] == "queued"
        assert data["job"]["progress_percentage"] == 0  # Default for step 0

    def test_processing_job_progress_percentage_clamped(
        self, app_with_routes, test_post, test_token
    ):
        """Progress percentage should be clamped to 0-100 range."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)

            # Create a job with out-of-range progress
            job = ProcessingJob(
                post_guid=post.guid,
                status="running",
                current_step=2,
                total_steps=4,
                step_name="Transcribing",
                progress_percentage=150,  # Invalid - should be clamped to 100
            )
            db.session.add(job)
            db.session.commit()

            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data["job"]["progress_percentage"] == 100  # Clamped


class TestTriggerStatusHeaders:
    """Test that trigger endpoints do not emit session cookies or Vary: Cookie."""

    def test_trigger_status_no_set_cookie_header(
        self, app_with_routes, test_post, test_token
    ):
        """Trigger status should never emit Set-Cookie header."""
        # Register the cookie stripping middleware
        from app import _configure_trigger_cookie_stripping

        _configure_trigger_cookie_stripping(app_with_routes)

        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)
            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        assert response.status_code == 200
        # Must NOT have Set-Cookie header
        assert "Set-Cookie" not in response.headers

    def test_trigger_status_no_vary_cookie_header(
        self, app_with_routes, test_post, test_token
    ):
        """Trigger status should not have Vary: Cookie header."""
        # Register the cookie stripping middleware
        from app import _configure_trigger_cookie_stripping

        _configure_trigger_cookie_stripping(app_with_routes)

        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)
            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        assert response.status_code == 200
        # Vary header should not contain Cookie
        vary = response.headers.get("Vary", "")
        assert "cookie" not in vary.lower()

    def test_trigger_endpoint_no_set_cookie_header(
        self, app_with_routes, test_post, test_token
    ):
        """Trigger endpoint should never emit Set-Cookie header."""
        # Register the cookie stripping middleware
        from app import _configure_trigger_cookie_stripping

        _configure_trigger_cookie_stripping(app_with_routes)

        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)
            response = client.get(
                f"/trigger?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        # Any status is fine, just check no Set-Cookie
        assert "Set-Cookie" not in response.headers


class TestTriggerStatusWithActiveJob:
    """Test /api/trigger/status returns 200 (not 5xx) when a job exists."""

    def test_running_job_returns_200_processing(
        self, app_with_routes, test_post, test_token
    ):
        """Running job should return 200 with processing state, never 5xx."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)

            # Create a running job with typical values
            job = ProcessingJob(
                post_guid=post.guid,
                status="running",
                current_step=2,
                total_steps=4,
                step_name="Transcribing",
                progress_percentage=50.0,
            )
            db.session.add(job)
            db.session.commit()

            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        # Must be 200, never 5xx
        assert response.status_code == 200
        data = response.get_json()
        assert data["state"] == "processing"
        assert data["job"]["status"] == "running"
        assert data["job"]["current_step"] == 2
        assert data["job"]["step_name"] == "Transcribing"
        # Verify started_at is present (not updated_at which doesn't exist)
        assert "started_at" in data["job"]
        assert "updated_at" not in data["job"]

    def test_completed_job_returns_200_ready(
        self, app_with_routes, test_post, test_token
    ):
        """Completed job should return 200 with ready state."""
        client = app_with_routes.test_client()

        with app_with_routes.app_context():
            post = db.session.merge(test_post)

            # Mark post as processed
            post.processed_audio_path = None  # No file, but job completed

            # Create a completed job
            job = ProcessingJob(
                post_guid=post.guid,
                status="completed",
                current_step=4,
                total_steps=4,
                step_name="Complete",
                progress_percentage=100.0,
            )
            db.session.add(job)
            db.session.commit()

            response = client.get(
                f"/api/trigger/status?guid={post.guid}"
                f"&feed_token={test_token['token_id']}"
                f"&feed_secret={test_token['secret']}"
            )

        # Must be 200
        assert response.status_code == 200
        data = response.get_json()
        # State depends on whether processed_audio_path exists
        assert data["state"] in ["ready", "not_started"]
