import datetime
import logging
import secrets
import time
from pathlib import Path
from threading import Lock, Thread
from typing import Any, cast
from urllib.parse import urlencode

import requests
import validators
from flask import (
    Blueprint,
    Flask,
    Response,
    current_app,
    g,
    jsonify,
    make_response,
    redirect,
    request,
    send_from_directory,
    url_for,
)
from flask.typing import ResponseReturnValue

from app.auth import is_auth_enabled
from app.auth.guards import require_admin
from app.auth.service import update_user_last_active
from app.extensions import db
from app.feeds import (
    _get_base_url,
    add_or_refresh_feed,
    generate_aggregate_feed_xml,
    generate_feed_xml,
    is_feed_active_for_user,
    refresh_feed,
)
from app.jobs_manager import get_jobs_manager
from app.models import (
    Feed,
    User,
    UserFeed,
)
from app.routes.feed_utils import (
    check_feed_allowance,
    cleanup_feed_directories,
    ensure_user_feed_membership,
    fix_url,
    handle_developer_mode_feed,
    user_feed_count,
    whitelist_latest_for_first_member,
)
from app.writer.client import writer_client

from .auth_routes import _require_authenticated_user as _auth_get_user

logger = logging.getLogger("global_logger")


feed_bp = Blueprint("feed", __name__)
_MISSING = object()

# Per-feed debounce so that bursty reader polls don't fan out into N background
# refresh threads. The scheduled `refresh_all_feeds` job
# (`src/app/background.py`) is the primary freshness mechanism; this just
# opportunistically nudges a single-feed refresh on read traffic without ever
# blocking the response. In-memory state is fine: a process restart simply
# resets the cooldown and the next poll triggers a fresh kickoff.
_BACKGROUND_REFRESH_LOCK = Lock()
_BACKGROUND_REFRESH_LAST_KICKOFF: dict[int, float] = {}
_AUTO_REFRESH_COOLDOWN_SECONDS = 60.0


def _parse_optional_feed_bool(
    payload: dict[str, Any],
    field_name: str,
) -> tuple[object, ResponseReturnValue | None]:
    if field_name not in payload:
        return _MISSING, None

    value = payload[field_name]
    if value is not None and not isinstance(value, bool):
        return (
            _MISSING,
            (
                jsonify({"error": f"{field_name} must be a boolean or null."}),
                400,
            ),
        )
    return value, None


def _build_feed_settings_updates(
    feed: Feed,
    payload: dict[str, Any],
) -> tuple[dict[str, Any] | None, ResponseReturnValue | None]:
    updates: dict[str, Any] = {}

    if "ad_detection_strategy" in payload:
        strategy = payload["ad_detection_strategy"]
        if strategy not in ("llm", "chapter", "chapter_insert"):
            return (
                None,
                (
                    jsonify(
                        {
                            "error": (
                                "Invalid ad_detection_strategy. Must be "
                                "'llm', 'chapter', or 'chapter_insert'"
                            )
                        }
                    ),
                    400,
                ),
            )
        updates["ad_detection_strategy"] = strategy

    if "chapter_filter_strings" in payload:
        filter_strings = payload["chapter_filter_strings"]
        if filter_strings is not None and not isinstance(filter_strings, str):
            return (
                None,
                (
                    jsonify(
                        {"error": "chapter_filter_strings must be a string or null"}
                    ),
                    400,
                ),
            )
        updates["chapter_filter_strings"] = filter_strings

    chapter_fallback_enabled, error_response = _parse_optional_feed_bool(
        payload,
        "enable_llm_chapter_fallback_tagging",
    )
    if error_response is not None:
        return None, error_response
    if chapter_fallback_enabled is not _MISSING:
        updates["enable_llm_chapter_fallback_tagging"] = chapter_fallback_enabled

    auto_whitelist_override, error_response = _parse_optional_feed_bool(
        payload,
        "auto_whitelist_new_episodes_override",
    )
    if error_response is not None:
        return None, error_response
    if auto_whitelist_override is not _MISSING:
        updates["auto_whitelist_new_episodes_override"] = auto_whitelist_override

    if "custom_llm_ad_prompt" in payload:
        custom_prompt = payload["custom_llm_ad_prompt"]
        if custom_prompt is not None and not isinstance(custom_prompt, str):
            return (
                None,
                (
                    jsonify({"error": "custom_llm_ad_prompt must be a string or null"}),
                    400,
                ),
            )
        updates["custom_llm_ad_prompt"] = custom_prompt

    resolved_strategy = updates.get(
        "ad_detection_strategy",
        getattr(feed, "ad_detection_strategy", "llm"),
    )
    if (
        resolved_strategy == "chapter_insert"
        and chapter_fallback_enabled is not _MISSING
        and chapter_fallback_enabled is False
    ):
        return (
            None,
            (
                jsonify(
                    {
                        "error": (
                            "enable_llm_chapter_fallback_tagging cannot be false "
                            "when ad_detection_strategy is 'chapter_insert'"
                        )
                    }
                ),
                400,
            ),
        )

    if not updates:
        return None, (jsonify({"error": "No settings provided."}), 400)

    return updates, None


@feed_bp.route("/feed", methods=["POST"])
def add_feed() -> ResponseReturnValue:
    settings = current_app.config.get("AUTH_SETTINGS")
    user = None
    if settings and settings.require_auth:
        user, error = _require_user_or_error()
        if error:
            return error
    url = request.form.get("url")
    if not url:
        return make_response(("URL is required", 400))

    url = fix_url(url)

    if current_app.config.get("developer_mode") and url.startswith("http://test-feed/"):
        return handle_developer_mode_feed(url, user)

    if not validators.url(url):
        return make_response(("Invalid URL", 400))

    try:
        if user:
            allowance_error = check_feed_allowance(user, url)
            if allowance_error:
                return allowance_error

        feed = add_or_refresh_feed(url)
        if user:
            created, previous_count = ensure_user_feed_membership(feed, user.id)
            if created and previous_count == 0:
                whitelist_latest_for_first_member(feed, getattr(user, "id", None))
        elif not is_auth_enabled():
            # In no-auth mode, if this feed has no members, trigger whitelisting for the latest post.
            if UserFeed.query.filter_by(feed_id=feed.id).count() == 0:
                whitelist_latest_for_first_member(feed, None)

        app = cast(Any, current_app)._get_current_object()
        Thread(
            target=_enqueue_pending_jobs_async,
            args=(app,),
            daemon=True,
            name="enqueue-jobs-after-add",
        ).start()
        return redirect(url_for("main.index"))
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error adding feed: {e}")
        return make_response((f"Error adding feed: {e}", 500))


@feed_bp.route("/api/feeds/<int:feed_id>/share-link", methods=["POST"])
def create_feed_share_link(feed_id: int) -> ResponseReturnValue:
    settings = current_app.config.get("AUTH_SETTINGS")
    if not settings or not settings.require_auth:
        return jsonify({"error": "Authentication is disabled."}), 404

    current = getattr(g, "current_user", None)
    if current is None:
        return jsonify({"error": "Authentication required."}), 401

    feed = Feed.query.get_or_404(feed_id)
    user = db.session.get(User, current.id)
    if user is None:
        return jsonify({"error": "User not found."}), 404

    result = writer_client.action(
        "create_feed_access_token",
        {"user_id": user.id, "feed_id": feed.id},
        wait=True,
    )
    if not result or not result.success or not isinstance(result.data, dict):
        return jsonify({"error": "Failed to create feed token"}), 500
    token_id = str(result.data["token_id"])
    secret = str(result.data["secret"])

    base_url = _get_base_url()
    path = f"/feed/{feed.id}"
    query = urlencode({"feed_token": token_id, "feed_secret": secret})
    prefilled_url = f"{base_url}{path}?{query}"

    return (
        jsonify(
            {
                "url": prefilled_url,
                "feed_token": token_id,
                "feed_secret": secret,
                "feed_id": feed.id,
            }
        ),
        201,
    )


@feed_bp.route("/api/feeds/search", methods=["GET"])
def search_feeds() -> ResponseReturnValue:
    term = (request.args.get("term") or "").strip()
    logger.info("Searching for podcasts with term: %s", term)
    if not term:
        return jsonify({"error": "term parameter is required"}), 400

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
        }
        response = requests.get(
            "http://api.podcastindex.org/search",
            headers=headers,
            params={"term": term},
            timeout=10,
        )
        response.raise_for_status()
        upstream_data = response.json()
    except requests.exceptions.RequestException as exc:
        logger.error("Podcast search request failed: %s", exc)
        return jsonify({"error": "Search request failed"}), 502
    except ValueError:
        logger.error("Podcast search returned non-JSON response")
        return (
            jsonify({"error": "Unexpected response from search provider"}),
            502,
        )

    results = upstream_data.get("results") or []
    transformed_results = []

    if current_app.config.get("developer_mode") and term.lower() == "test":
        logger.info("Developer mode test search - adding mock results")
        for i in range(1, 11):
            transformed_results.append(
                {
                    "title": f"Test Feed {i}",
                    "author": "Test Author",
                    "feedUrl": f"http://test-feed/{i}",
                    "artwork": "https://via.placeholder.com/150",
                    "genres": ["Test Genre"],
                }
            )
    else:
        logger.info(
            "(dev mode disabled) Podcast search returned %d results", len(results)
        )

    for item in results:
        feed_url = item.get("feedUrl")
        if not feed_url:
            continue

        transformed_results.append(
            {
                "title": item.get("collectionName")
                or item.get("trackName")
                or "Unknown title",
                "author": item.get("artistName") or "",
                "feedUrl": feed_url,
                "artworkUrl": item.get("artworkUrl100")
                or item.get("artworkUrl600")
                or "",
                "description": item.get("collectionCensoredName")
                or item.get("trackCensoredName")
                or "",
                "genres": item.get("genres") or [],
            }
        )

    total = upstream_data.get("resultCount")
    if not isinstance(total, int) or total == 0:
        total = len(transformed_results)

    return jsonify(
        {
            "results": transformed_results,
            "total": total,
        }
    )


def _should_kickoff_async_refresh(feed_id: int) -> bool:
    """True iff the per-feed cooldown has elapsed; reserves the next slot."""
    now = time.monotonic()
    with _BACKGROUND_REFRESH_LOCK:
        last = _BACKGROUND_REFRESH_LAST_KICKOFF.get(feed_id)
        if last is not None and now - last < _AUTO_REFRESH_COOLDOWN_SECONDS:
            return False
        _BACKGROUND_REFRESH_LAST_KICKOFF[feed_id] = now
        return True


def _spawn_async_refresh(app: Flask, feed_id: int) -> None:
    Thread(
        target=_refresh_feed_background,
        args=(app, feed_id),
        daemon=True,
        name=f"feed-auto-refresh-{feed_id}",
    ).start()


@feed_bp.route("/feed/<int:f_id>", methods=["GET"])
def get_feed(f_id: int) -> Response:
    if hasattr(g, "current_user") and g.current_user:
        update_user_last_active(g.current_user.id)

    feed = Feed.query.get_or_404(f_id)

    # Don't block the response on an upstream RSS fetch. The scheduled
    # `refresh_all_feeds` job is the primary freshness source; we additionally
    # nudge a per-feed refresh on read traffic, debounced so bursty pollers
    # don't fan out into N threads.
    if _should_kickoff_async_refresh(f_id):
        app = cast(Any, current_app)._get_current_object()
        _spawn_async_refresh(app, f_id)

    xml_content = generate_feed_xml(feed)

    response = make_response(xml_content)
    response.headers["Content-Type"] = "application/rss+xml"
    return response


@feed_bp.route("/feed/<int:f_id>", methods=["DELETE"])
def delete_feed(f_id: int) -> ResponseReturnValue:
    user, error = _require_user_or_error(allow_missing_auth=True)
    if error:
        return error

    feed = Feed.query.get_or_404(f_id)
    if user is not None and user.role != "admin":
        return (
            jsonify({"error": "Only administrators can delete feeds."}),
            403,
        )

    # Get all post IDs for this feed
    post_ids = [post.id for post in feed.posts]

    # Delete audio files if they exist
    for post in feed.posts:
        if post.unprocessed_audio_path and Path(post.unprocessed_audio_path).exists():
            try:
                Path(post.unprocessed_audio_path).unlink()
                logger.info(f"Deleted unprocessed audio: {post.unprocessed_audio_path}")
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Error deleting unprocessed audio {post.unprocessed_audio_path}: {e}"
                )

        if post.processed_audio_path and Path(post.processed_audio_path).exists():
            try:
                Path(post.processed_audio_path).unlink()
                logger.info(f"Deleted processed audio: {post.processed_audio_path}")
            except Exception as e:  # noqa: BLE001
                logger.error(
                    f"Error deleting processed audio {post.processed_audio_path}: {e}"
                )

    # Clean up directory structures
    cleanup_feed_directories(feed)

    try:
        result = writer_client.action(
            "delete_feed_cascade", {"feed_id": feed.id}, wait=True
        )
        if not result or not result.success:
            raise RuntimeError(getattr(result, "error", "Failed to delete feed"))
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to delete feed %s: %s", feed.id, e)
        return make_response(("Failed to delete feed", 500))

    logger.info(
        f"Deleted feed: {feed.title} (ID: {feed.id}) with {len(post_ids)} posts"
    )
    return make_response("", 204)


@feed_bp.route("/api/feeds/<int:f_id>/refresh", methods=["POST"])
def refresh_feed_endpoint(f_id: int) -> ResponseReturnValue:
    """
    Refresh the specified feed and return a JSON response indicating the result.
    """
    if hasattr(g, "current_user") and g.current_user:
        update_user_last_active(g.current_user.id)

    feed = Feed.query.get_or_404(f_id)
    feed_title = feed.title
    app = cast(Any, current_app)._get_current_object()

    Thread(
        target=_refresh_feed_background,
        args=(app, f_id),
        daemon=True,
        name=f"feed-refresh-{f_id}",
    ).start()

    return (
        jsonify(
            {
                "status": "accepted",
                "message": f'Feed "{feed_title}" refresh queued for processing',
            }
        ),
        202,
    )


@feed_bp.route("/api/feeds/<int:feed_id>/settings", methods=["PATCH"])
def update_feed_settings_endpoint(feed_id: int) -> ResponseReturnValue:
    _, error_response = require_admin("update feed settings")
    if error_response is not None:
        return error_response

    feed = Feed.query.get_or_404(feed_id)
    payload = request.get_json(silent=True) or {}
    updates, error_response = _build_feed_settings_updates(feed, payload)
    if error_response is not None:
        return error_response
    if updates is None:
        return jsonify({"error": "No settings provided."}), 400

    result = writer_client.update("Feed", feed_id, updates, wait=True)
    if result is None or not result.success:
        return (
            jsonify({"error": getattr(result, "error", "Failed to update feed")}),
            500,
        )

    # The writer may commit in a separate process/session; expire local state so the
    # response reflects the newly persisted values instead of any cached identity-map
    # object loaded earlier in this request.
    db.session.expire_all()
    feed = db.session.get(Feed, feed_id)
    if feed is None:
        return jsonify({"error": "Feed not found"}), 404

    return jsonify(_serialize_feed(feed, current_user=getattr(g, "current_user", None)))


@feed_bp.route("/api/feeds/<int:feed_id>/subscribers", methods=["GET"])
def get_feed_subscribers(feed_id: int) -> ResponseReturnValue:
    """Return subscriber list for a feed (admin only)."""
    _, error_response = require_admin("view feed subscribers")
    if error_response is not None:
        return error_response

    feed = db.session.get(Feed, feed_id)
    if feed is None:
        return jsonify({"error": "Feed not found"}), 404

    subscribers = []
    for uf in cast(list[UserFeed], feed.user_feeds):
        u = uf.user
        if u is None:
            continue
        subscribers.append(
            {
                "user_id": u.id,
                "username": u.username,
                "role": u.role,
                "subscription_status": u.feed_subscription_status,
                "joined_at": uf.created_at.isoformat() if uf.created_at else None,
            }
        )

    return jsonify({"feed_id": feed_id, "subscribers": subscribers})


def _refresh_feed_background(app: Flask, feed_id: int) -> None:
    with app.app_context():
        feed = db.session.get(Feed, feed_id)
        if not feed:
            logger.warning("Feed %s disappeared before refresh could run", feed_id)
            return

        try:
            refresh_feed(feed)
            get_jobs_manager().enqueue_pending_jobs(
                trigger="feed_refresh", context={"feed_id": feed_id}
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to refresh feed %s asynchronously: %s", feed_id, exc)


def _enqueue_pending_jobs_async(app: Flask) -> None:
    with app.app_context():
        try:
            get_jobs_manager().enqueue_pending_jobs(trigger="feed_refresh")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to enqueue pending jobs asynchronously: %s", exc)


@feed_bp.route("/api/feeds/refresh-all", methods=["POST"])
def refresh_all_feeds_endpoint() -> Response:
    """Trigger a refresh for all feeds and enqueue pending jobs."""
    if hasattr(g, "current_user") and g.current_user:
        update_user_last_active(g.current_user.id)

    result = get_jobs_manager().start_refresh_all_feeds(trigger="manual_refresh")
    feed_count = Feed.query.count()
    return jsonify(
        {
            "status": "success",
            "feeds_refreshed": feed_count,
            "jobs_enqueued": result.get("enqueued", 0),
        }
    )


@feed_bp.route("/<path:something_or_rss>", methods=["GET"])
def get_feed_by_alt_or_url(something_or_rss: str) -> Response:
    # first try to serve ANY static file matching the path
    if current_app.static_folder is not None:
        # Use Flask's safe helper to prevent directory traversal outside static_folder
        try:
            return send_from_directory(current_app.static_folder, something_or_rss)
        except Exception:  # noqa: BLE001
            # Not a valid static file; fall through to RSS/DB lookup
            pass
    feed = Feed.query.filter_by(rss_url=something_or_rss).first()
    if feed:
        xml_content = generate_feed_xml(feed)
        response = make_response(xml_content)
        response.headers["Content-Type"] = "application/rss+xml"
        return response

    return make_response(("Feed not found", 404))


@feed_bp.route("/feeds", methods=["GET"])
def api_feeds() -> ResponseReturnValue:
    settings = current_app.config.get("AUTH_SETTINGS")
    if settings and settings.require_auth:
        user, error = _require_user_or_error()
        if error:
            return error
        if user and user.role != "admin":
            feeds = (
                Feed.query.join(UserFeed, UserFeed.feed_id == Feed.id)
                .filter(UserFeed.user_id == user.id)
                .all()
            )
            # Hack: Always include Feed 1
            feed_1 = Feed.query.get(1)
            if feed_1 and feed_1 not in feeds:
                feeds.append(feed_1)
        else:
            feeds = Feed.query.all()
        current_user = user
    else:
        feeds = Feed.query.all()
        current_user = getattr(g, "current_user", None)

    feeds_data = [_serialize_feed(feed, current_user=current_user) for feed in feeds]
    return jsonify(feeds_data)


@feed_bp.route("/api/feeds/<int:feed_id>/join", methods=["POST"])
def api_join_feed(feed_id: int) -> ResponseReturnValue:
    user, error = _require_user_or_error()
    if error:
        return error
    if user is None:
        return jsonify({"error": "Authentication required."}), 401

    feed = Feed.query.get_or_404(feed_id)
    existing_membership = UserFeed.query.filter_by(
        feed_id=feed.id, user_id=user.id
    ).first()
    if user.role != "admin":
        # Use manual allowance if set, otherwise fall back to plan allowance
        allowance = user.manual_feed_allowance
        if allowance is None:
            allowance = getattr(user, "feed_allowance", 0) or 0

        at_capacity = allowance > 0 and user_feed_count(user.id) >= allowance
        missing_membership = existing_membership is None
        if at_capacity and missing_membership:
            return (
                jsonify(
                    {
                        "error": "FEED_LIMIT_REACHED",
                        "message": f"Your plan allows {allowance} feeds. Increase your plan to add more.",
                        "feeds_in_use": user_feed_count(user.id),
                        "feed_allowance": allowance,
                    }
                ),
                402,
            )
    if existing_membership:
        refreshed = Feed.query.get(feed_id)
        return jsonify(_serialize_feed(refreshed or feed, current_user=user)), 200

    created, previous_count = ensure_user_feed_membership(
        feed, getattr(user, "id", None)
    )
    if created and previous_count == 0:
        whitelist_latest_for_first_member(feed, getattr(user, "id", None))
    refreshed = Feed.query.get(feed_id)
    return (
        jsonify(_serialize_feed(refreshed or feed, current_user=user)),
        200,
    )


@feed_bp.route("/api/feeds/<int:feed_id>/exit", methods=["POST"])
def api_exit_feed(feed_id: int) -> ResponseReturnValue:
    user, error = _require_user_or_error()
    if error:
        return error
    if user is None:
        return jsonify({"error": "Authentication required."}), 401

    feed = Feed.query.get_or_404(feed_id)
    writer_client.action(
        "remove_user_feed_membership",
        {"feed_id": feed.id, "user_id": user.id},
        wait=True,
    )
    refreshed = Feed.query.get(feed_id)
    return (
        jsonify(_serialize_feed(refreshed or feed, current_user=user)),
        200,
    )


@feed_bp.route("/api/feeds/<int:feed_id>/leave", methods=["POST"])
def api_leave_feed(feed_id: int) -> ResponseReturnValue:
    """Remove current user membership; hide from their view."""
    user, error = _require_user_or_error()
    if error:
        return error
    if user is None:
        return jsonify({"error": "Authentication required."}), 401

    feed = Feed.query.get_or_404(feed_id)
    writer_client.action(
        "remove_user_feed_membership",
        {"feed_id": feed.id, "user_id": user.id},
        wait=True,
    )
    return jsonify({"status": "ok", "feed_id": feed.id})


@feed_bp.route("/feed/user/<int:user_id>", methods=["GET"])
def get_user_aggregate_feed(user_id: int) -> Response:
    """Serve the aggregate RSS feed for a specific user."""
    # Auth check is handled by middleware via feed_token
    # If auth is disabled, this is public.
    # If auth is enabled, middleware ensures we have a valid token for this user_id.

    if is_auth_enabled():
        current = getattr(g, "current_user", None)
        if current is None:
            return make_response(("Authentication required", 401))
        if current.role != "admin" and current.id != user_id:
            return make_response(("Forbidden", 403))

    user = db.session.get(User, user_id)
    if not user:
        if user_id == 0 and not is_auth_enabled():
            # Support anonymous aggregate feed when auth is disabled
            xml_content = generate_aggregate_feed_xml(None)
            response = make_response(xml_content)
            response.headers["Content-Type"] = "application/rss+xml"
            return response
        return make_response(("User not found", 404))

    xml_content = generate_aggregate_feed_xml(user)
    response = make_response(xml_content)
    response.headers["Content-Type"] = "application/rss+xml"
    return response


@feed_bp.route("/feed/aggregate", methods=["GET"])
def get_aggregate_feed_redirect() -> ResponseReturnValue:
    """Convenience endpoint to redirect to the user's aggregate feed."""
    settings = current_app.config.get("AUTH_SETTINGS")

    # Case 1: Auth Disabled -> Redirect to Admin User (or ID 0 if none exist)
    if not settings or not settings.require_auth:
        admin = User.query.filter_by(role="admin").first()
        user_id = admin.id if admin else 0
        return redirect(url_for("feed.get_user_aggregate_feed", user_id=user_id))

    # Case 2: Auth Enabled -> Require explicit user link
    # We cannot easily determine "current user" for a podcast player without a token.
    # If accessed via browser with session, we could redirect, but for consistency
    # we should probably just tell them to get their link.

    current = getattr(g, "current_user", None)
    if current:
        return redirect(url_for("feed.get_user_aggregate_feed", user_id=current.id))

    return (
        jsonify(
            {
                "error": "Authentication required",
                "message": "Please use your unique aggregate feed URL from the dashboard.",
            }
        ),
        401,
    )


@feed_bp.route("/api/user/aggregate-link", methods=["POST"])
def create_aggregate_feed_link() -> ResponseReturnValue:
    """Generate a unique RSS link for the current user's aggregate feed."""
    settings = current_app.config.get("AUTH_SETTINGS")
    user, error = _resolve_aggregate_link_user_or_error(settings)
    if error:
        return error

    if user is None:
        return jsonify({"error": "Authentication required."}), 401

    # Create a token with feed_id=None (Aggregate Token)
    result = writer_client.action(
        "create_feed_access_token",
        {"user_id": user.id, "feed_id": None},
        wait=True,
    )
    if not result or not result.success or not isinstance(result.data, dict):
        return jsonify({"error": "Failed to create aggregate feed token"}), 500

    token_id = str(result.data["token_id"])
    secret = str(result.data["secret"])

    base_url = _get_base_url()
    path = f"/feed/user/{user.id}"

    # If auth is disabled, we don't strictly need the token params,
    # but including them doesn't hurt and ensures the link works if auth is enabled later.
    # However, to keep it clean for single-user mode:
    settings = current_app.config.get("AUTH_SETTINGS")
    if settings and settings.require_auth:
        query = urlencode({"feed_token": token_id, "feed_secret": secret})
    else:
        query = ""

    full_url = f"{base_url}{path}"
    if query:
        full_url = f"{full_url}?{query}"

    return (
        jsonify(
            {
                "url": full_url,
                "feed_token": token_id,
                "feed_secret": secret,
            }
        ),
        201,
    )


def _resolve_aggregate_link_user_or_error(
    settings: Any,
) -> tuple[User | None, ResponseReturnValue | None]:
    if settings and settings.require_auth:
        return _require_user_or_error()
    return _get_or_create_default_aggregate_user()


def _get_or_create_default_aggregate_user() -> tuple[
    User | None, ResponseReturnValue | None
]:
    user = User.query.filter_by(role="admin").first() or User.query.first()
    if user is not None:
        return user, None

    result = writer_client.action(
        "create_user",
        {
            "username": "admin",
            "password": secrets.token_urlsafe(16),
            "role": "admin",
        },
        wait=True,
    )
    if result and result.success and isinstance(result.data, dict):
        user_id = result.data.get("user_id")
        if user_id:
            user = db.session.get(User, user_id)

    if user is None:
        return None, (
            jsonify({"error": "No user found and failed to create one."}),
            500,
        )

    return user, None


def _require_user_or_error(
    allow_missing_auth: bool = False,
) -> tuple[User | None, ResponseReturnValue | None]:
    settings = current_app.config.get("AUTH_SETTINGS")
    if not settings or not settings.require_auth:
        if allow_missing_auth:
            return None, None
        return None, (jsonify({"error": "Authentication is disabled."}), 404)

    current = getattr(g, "current_user", None)
    if current is None:
        return None, (jsonify({"error": "Authentication required."}), 401)

    user = _auth_get_user()
    if user is None:
        return None, (jsonify({"error": "User not found."}), 404)

    return user, None


def _latest_episode_release_date(feed: Feed) -> str | None:
    latest_release_date: datetime.datetime | None = None

    for post in cast(list[Any], getattr(feed, "posts", [])):
        release_date = getattr(post, "release_date", None)
        if release_date is None:
            continue

        normalized_release_date = release_date
        if normalized_release_date.tzinfo is None:
            normalized_release_date = normalized_release_date.replace(
                tzinfo=datetime.UTC
            )
        else:
            normalized_release_date = normalized_release_date.astimezone(datetime.UTC)

        if latest_release_date is None or normalized_release_date > latest_release_date:
            latest_release_date = normalized_release_date

    return latest_release_date.isoformat() if latest_release_date else None


def _serialize_feed(
    feed: Feed,
    *,
    current_user: User | None = None,
) -> dict[str, Any]:
    auth_enabled = is_auth_enabled()
    member_ids = [membership.user_id for membership in getattr(feed, "user_feeds", [])]

    # In no-auth mode, everyone is functionally a member.
    is_member = not auth_enabled or bool(
        current_user and getattr(current_user, "id", None) in member_ids
    )

    # Hack: Always treat Feed 1 as a member
    if feed.id == 1 and (current_user or not auth_enabled):
        is_member = True

    is_active_subscription = False
    if is_member:
        if current_user:
            is_active_subscription = is_feed_active_for_user(feed.id, current_user)
        elif not auth_enabled:
            is_active_subscription = True

    feed_payload = {
        "id": feed.id,
        "title": feed.title,
        "rss_url": feed.rss_url,
        "description": feed.description,
        "author": feed.author,
        "image_url": feed.image_url,
        "auto_whitelist_new_episodes_override": getattr(
            feed, "auto_whitelist_new_episodes_override", None
        ),
        "posts_count": len(cast(list[Any], feed.posts)),
        "latest_episode_release_date": _latest_episode_release_date(feed),
        "member_count": len(member_ids),
        "is_member": is_member,
        "is_active_subscription": is_active_subscription,
        "ad_detection_strategy": getattr(feed, "ad_detection_strategy", "llm"),
        "chapter_filter_strings": getattr(feed, "chapter_filter_strings", None),
        "enable_llm_chapter_fallback_tagging": getattr(
            feed, "enable_llm_chapter_fallback_tagging", None
        ),
        "custom_llm_ad_prompt": getattr(feed, "custom_llm_ad_prompt", None),
    }
    return feed_payload
