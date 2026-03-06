import logging
import os

import flask
import werkzeug.exceptions
from flask import Blueprint, current_app, g, send_from_directory

from app.extensions import db
from app.models import Feed, Post
from app.runtime_config import config

logger = logging.getLogger("global_logger")


main_bp = Blueprint("main", __name__)


def _require_legacy_endpoint_auth() -> flask.Response | None:
    """Require authentication for legacy mutating routes when auth is enabled."""
    settings = current_app.config.get("AUTH_SETTINGS")
    if not settings or not settings.require_auth:
        return None  # Auth disabled — allow without login

    if getattr(g, "current_user", None) is None:
        return flask.make_response(("Authentication required.", 401))

    return None


@main_bp.route("/")
def index() -> flask.Response:
    """Serve the React app's index.html."""
    static_folder = current_app.static_folder
    if static_folder and os.path.exists(os.path.join(static_folder, "index.html")):
        return send_from_directory(static_folder, "index.html")

    feeds = Feed.query.all()
    return flask.make_response(
        flask.render_template("index.html", feeds=feeds, config=config), 200
    )


def _should_serve_spa_fallback(path: str) -> bool:
    """Only treat extensionless paths as React routes.

    Requests for missing files should return 404 instead of silently serving
    index.html, otherwise PWA/TWA checks end up receiving HTML for files like
    /.well-known/assetlinks.json and /manifest.json.
    """
    if path.startswith(".well-known/"):
        return False

    return os.path.splitext(path)[1] == ""


def _build_assetlinks_payload() -> list[dict[str, object]] | None:
    package_name = os.environ.get("PODLY_ANDROID_PACKAGE_NAME", "").strip()
    raw_fingerprints = os.environ.get("PODLY_ANDROID_SHA256_CERT_FINGERPRINTS", "")
    fingerprints = [value.strip() for value in raw_fingerprints.split(",") if value.strip()]

    if not package_name or not fingerprints:
        return None

    return [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": package_name,
                "sha256_cert_fingerprints": fingerprints,
            },
        }
    ]


@main_bp.route("/.well-known/assetlinks.json")
def assetlinks() -> flask.Response:
    """Serve Digital Asset Links for Android wrappers and TWAs."""
    static_folder = current_app.static_folder
    if static_folder:
        static_path = os.path.join(static_folder, ".well-known", "assetlinks.json")
        if os.path.exists(static_path):
            return send_from_directory(static_folder, ".well-known/assetlinks.json")

    payload = _build_assetlinks_payload()
    if payload is not None:
        return flask.jsonify(payload)

    flask.abort(404)


@main_bp.route("/<path:path>")
def catch_all(path: str) -> flask.Response:
    """Serve React app for all frontend routes, or serve static files."""
    # Don't handle API routes - let them be handled by API blueprint
    if path.startswith("api/"):
        flask.abort(404)

    static_folder = current_app.static_folder
    if static_folder:
        # Try to serve a static file; send_from_directory validates path safety
        try:
            return send_from_directory(static_folder, path)
        except werkzeug.exceptions.NotFound:
            pass

        if _should_serve_spa_fallback(path):
            # Route-like URLs are handled by the React router.
            try:
                return send_from_directory(static_folder, "index.html")
            except werkzeug.exceptions.NotFound:
                pass

    # Fallback to 404
    flask.abort(404)


@main_bp.route("/feed/<int:f_id>/toggle-whitelist-all/<val>", methods=["POST"])
def whitelist_all(f_id: int, val: str) -> flask.Response:
    auth_error = _require_legacy_endpoint_auth()
    if auth_error is not None:
        return auth_error

    feed = Feed.query.get_or_404(f_id)
    for post in feed.posts:
        post.whitelisted = val.lower() == "true"
    db.session.commit()
    return flask.make_response("", 200)


@main_bp.route("/set_whitelist/<string:p_guid>/<val>", methods=["POST"])
def set_whitelist(p_guid: str, val: str) -> flask.Response:
    auth_error = _require_legacy_endpoint_auth()
    if auth_error is not None:
        return auth_error

    logger.info(f"Setting whitelist status for post with GUID: {p_guid} to {val}")
    post = Post.query.filter_by(guid=p_guid).first()
    if post is None:
        return flask.make_response(("Post not found", 404))

    post.whitelisted = val.lower() == "true"
    db.session.commit()

    return index()
