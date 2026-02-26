"""Admin cost dashboard API endpoints.

Calculates platform costs on-the-fly from existing tables — no migrations needed.
Cost model: $0.04/hour x episode_duration / subscriber_count per user.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import flask
from flask import Blueprint, jsonify, request

from app.auth.guards import require_admin
from app.extensions import db
from app.models import Feed, ModelCall, Post, ProcessingJob, User, UserFeed
from app.writer.client import writer_client

logger = logging.getLogger("global_logger")

costs_bp = Blueprint("costs", __name__)

# Cost rate: $0.04 per hour of audio processed
COST_RATE_PER_HOUR = 0.04


def _compute_cost_per_subscriber(duration_seconds: int, subscriber_count: int) -> float:
    """Cost attributed per subscriber for one episode."""
    if subscriber_count <= 0 or duration_seconds <= 0:
        return 0.0
    hours = duration_seconds / 3600.0
    return COST_RATE_PER_HOUR * hours / subscriber_count


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    import calendar

    start = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59)
    return start, end


@costs_bp.route("/api/admin/costs", methods=["GET"])
def api_admin_costs() -> flask.Response:
    """Return platform cost data for the admin dashboard.

    Query params:
      year  (int, default=current year)
      month (int, default=current month)
    """
    _, error_response = require_admin("view cost data")
    if error_response:
        return error_response

    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        year = int(request.args.get("year", now.year))
        month = int(request.args.get("month", now.month))
    except (ValueError, TypeError):
        return flask.make_response(jsonify({"error": "Invalid year or month"}), 400)

    month_start, month_end = _month_range(year, month)

    # --- Users ---
    users: list[User] = User.query.order_by(User.username).all()

    # --- Feeds and subscriber counts ---
    feeds: list[Feed] = Feed.query.all()
    feed_subscriber_count: dict[int, int] = {}
    for feed in feeds:
        feed_subscriber_count[feed.id] = len(feed.user_feeds)

    # --- Processed posts in date range (by completed_at on jobs) ---
    completed_jobs: list[ProcessingJob] = ProcessingJob.query.filter(
        ProcessingJob.status == "completed",
        ProcessingJob.completed_at >= month_start,
        ProcessingJob.completed_at <= month_end,
    ).all()

    # Map post_guid -> job for the month
    job_by_guid: dict[str, ProcessingJob] = {}
    for job in completed_jobs:
        # Keep the latest completed job per post
        existing = job_by_guid.get(job.post_guid)
        if existing is None or (job.completed_at or datetime.min) > (
            existing.completed_at or datetime.min
        ):
            job_by_guid[job.post_guid] = job

    # Fetch posts for these guids
    guids = list(job_by_guid.keys())
    posts_in_month: list[Post] = (
        Post.query.filter(Post.guid.in_(guids)).all() if guids else []
    )
    post_map: dict[str, Post] = {p.guid: p for p in posts_in_month}

    # --- Per-user monthly cost breakdown ---
    user_feed_map: dict[int, list[int]] = {}  # user_id -> [feed_id, ...]
    feed_user_map: dict[int, list[int]] = {}  # feed_id -> [user_id, ...]
    for uf in UserFeed.query.all():
        user_feed_map.setdefault(uf.user_id, []).append(uf.feed_id)
        feed_user_map.setdefault(uf.feed_id, []).append(uf.user_id)

    # For each completed post this month, attribute cost to each subscriber
    user_costs: dict[int, float] = {u.id: 0.0 for u in users}
    feed_costs: dict[int, float] = {f.id: 0.0 for f in feeds}
    feed_episode_counts: dict[int, int] = {f.id: 0 for f in feeds}

    for guid, _job in job_by_guid.items():
        post = post_map.get(guid)
        if not post:
            continue
        duration = post.duration or 0
        feed_id = post.feed_id
        subscriber_count = feed_subscriber_count.get(feed_id, 0)
        cost_per_sub = _compute_cost_per_subscriber(duration, subscriber_count)
        total_episode_cost = (
            COST_RATE_PER_HOUR * (duration / 3600.0) if duration > 0 else 0.0
        )

        feed_costs[feed_id] = feed_costs.get(feed_id, 0.0) + total_episode_cost
        feed_episode_counts[feed_id] = feed_episode_counts.get(feed_id, 0) + 1

        for uf_user_id in feed_user_map.get(feed_id, []):
            user_costs[uf_user_id] = user_costs.get(uf_user_id, 0.0) + cost_per_sub

    # --- Build per-user data ---
    users_data: list[dict[str, Any]] = []
    for user in users:
        sub_amount_cents = None
        if user.stripe_subscription_id:
            from app.billing_cache import fetch_subscription_amount

            sub_amount_cents = fetch_subscription_amount(user.stripe_subscription_id)

        feed_ids = user_feed_map.get(user.id, [])
        users_data.append(
            {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "feed_count": len(feed_ids),
                "subscription_status": user.feed_subscription_status,
                "stripe_subscription_id": user.stripe_subscription_id,
                "subscription_amount_cents": sub_amount_cents,
                "monthly_cost": round(user_costs.get(user.id, 0.0), 4),
            }
        )

    # --- Per-feed breakdown ---
    feeds_data: list[dict[str, Any]] = []
    for feed in feeds:
        feeds_data.append(
            {
                "id": feed.id,
                "title": feed.title,
                "subscriber_count": feed_subscriber_count.get(feed.id, 0),
                "episodes_this_month": feed_episode_counts.get(feed.id, 0),
                "monthly_cost": round(feed_costs.get(feed.id, 0.0), 4),
            }
        )
    feeds_data.sort(key=lambda f: f["monthly_cost"], reverse=True)

    total_cost = round(sum(feed_costs.values()), 4)

    return jsonify(
        {
            "year": year,
            "month": month,
            "total_cost": total_cost,
            "cost_rate_per_hour": COST_RATE_PER_HOUR,
            "users": users_data,
            "feeds": feeds_data,
        }
    )


@costs_bp.route("/api/admin/costs/calls", methods=["GET"])
def api_admin_costs_calls() -> flask.Response:
    """Paginated log of LLM and Whisper API calls."""
    _, error_response = require_admin("view cost data")
    if error_response:
        return error_response

    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(200, max(1, int(request.args.get("per_page", 50))))
    except (ValueError, TypeError):
        return flask.make_response(jsonify({"error": "Invalid pagination params"}), 400)

    total = db.session.query(ModelCall).count()
    calls: list[ModelCall] = (
        ModelCall.query.order_by(ModelCall.timestamp.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    calls_data = [
        {
            "id": c.id,
            "post_id": c.post_id,
            "model_name": c.model_name,
            "status": c.status,
            "timestamp": c.timestamp.isoformat() if c.timestamp else None,
            "retry_attempts": c.retry_attempts,
        }
        for c in calls
    ]

    return jsonify(
        {
            "calls": calls_data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }
    )


@costs_bp.route("/api/admin/costs/cleanup/cancelled-feeds", methods=["POST"])
def api_admin_cleanup_cancelled_feeds() -> flask.Response:
    """Remove feeds whose only subscribers have cancelled subscriptions."""
    _, error_response = require_admin("perform cleanup")
    if error_response:
        return error_response

    # Find feeds where all subscribers have 'inactive' or 'cancelled' status
    feeds: list[Feed] = Feed.query.all()
    removed = 0
    for feed in feeds:
        if not feed.user_feeds:
            continue
        all_cancelled = all(
            uf.user and uf.user.feed_subscription_status in ("inactive", "cancelled")
            for uf in feed.user_feeds
        )
        if all_cancelled:
            result = writer_client.action(
                "delete_feed_cascade", {"feed_id": feed.id}, wait=False
            )
            if result and result.success:
                removed += 1
                logger.info(
                    "[COSTS] Removed cancelled-subscriber feed id=%s title=%s",
                    feed.id,
                    feed.title,
                )

    return jsonify({"removed": removed})


@costs_bp.route("/api/admin/costs/cleanup/orphan-feeds", methods=["POST"])
def api_admin_cleanup_orphan_feeds() -> flask.Response:
    """Delete feeds with no subscribers at all."""
    _, error_response = require_admin("perform cleanup")
    if error_response:
        return error_response

    feeds: list[Feed] = Feed.query.all()
    removed = 0
    for feed in feeds:
        if not feed.user_feeds:
            result = writer_client.action(
                "delete_feed_cascade", {"feed_id": feed.id}, wait=False
            )
            if result and result.success:
                removed += 1
                logger.info(
                    "[COSTS] Removed orphan feed id=%s title=%s", feed.id, feed.title
                )

    return jsonify({"removed": removed})
