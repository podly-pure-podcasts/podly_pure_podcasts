"""Admin cost dashboard API endpoints.

Calculates platform costs on-the-fly from existing tables.
Cost model: LiteLLM token pricing + the configured Whisper duration rate,
attributed across subscribers.
"""

import logging
from datetime import UTC, datetime
from typing import Any

import flask
from flask import Blueprint, jsonify, request

from app.auth.guards import require_admin
from app.config_store import read_combined
from app.extensions import db
from app.llm_pricing import (
    compute_model_call_cost as _model_call_cost,
)
from app.llm_pricing import (
    is_billable_llm_call as _is_billable_llm_call,
)
from app.llm_pricing import (
    is_whisper_call as _is_whisper_call_by_name,
)
from app.model_call_token_backfill import backfill_model_call_token_usage
from app.models import (
    Feed,
    ModelCall,
    Post,
    ProcessingJob,
    TranscriptSegment,
    User,
    UserFeed,
)
from app.runtime_config import config as runtime_config
from app.writer.client import writer_client
from shared import defaults as DEFAULTS

logger = logging.getLogger("global_logger")

costs_bp = Blueprint("costs", __name__)


def _compute_cost_per_subscriber(
    total_episode_cost: float, subscriber_count: int
) -> float:
    """Cost attributed per subscriber for one episode."""
    if subscriber_count <= 0 or total_episode_cost <= 0:
        return 0.0
    return total_episode_cost / subscriber_count


def _has_token_usage(call: ModelCall) -> bool:
    return bool(
        call.prompt_tokens or call.cached_prompt_tokens or call.completion_tokens
    )


def _persisted_or_computed_cost(call: ModelCall) -> float:
    """Cost stored when the call was finalized; legacy rows without one (or with
    a stale zero despite token usage) are priced from their token usage."""
    stored = call.estimated_cost_usd
    if stored is not None and not (stored == 0 and _has_token_usage(call)):
        return float(stored)
    if not _has_token_usage(call):
        return 0.0
    return _model_call_cost(call)


def _is_whisper_call(call: ModelCall) -> bool:
    return _is_whisper_call_by_name(call.model_name, call.prompt)


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    import calendar

    start = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59)
    return start, end


def _latest_completed_jobs_by_guid(
    month_start: datetime, month_end: datetime
) -> dict[str, ProcessingJob]:
    completed_jobs: list[ProcessingJob] = ProcessingJob.query.filter(
        ProcessingJob.status == "completed",
        ProcessingJob.completed_at >= month_start,
        ProcessingJob.completed_at <= month_end,
    ).all()

    job_by_guid: dict[str, ProcessingJob] = {}
    for job in completed_jobs:
        existing = job_by_guid.get(job.post_guid)
        if existing is None or (job.completed_at or datetime.min) > (
            existing.completed_at or datetime.min
        ):
            job_by_guid[job.post_guid] = job
    return job_by_guid


def _transcript_end_by_post_id(post_ids: list[int]) -> dict[int, float]:
    if not post_ids:
        return {}
    rows = (
        db.session.query(
            TranscriptSegment.post_id, db.func.max(TranscriptSegment.end_time)
        )
        .filter(TranscriptSegment.post_id.in_(post_ids))
        .group_by(TranscriptSegment.post_id)
        .all()
    )
    return {post_id: float(end_time) for post_id, end_time in rows}


def _model_calls_by_post_id(post_ids: list[int]) -> dict[int, list[ModelCall]]:
    if not post_ids:
        return {}
    model_calls = (
        ModelCall.query.filter(
            ModelCall.post_id.in_(post_ids),
            ModelCall.status.like("success%"),
        )
        .order_by(ModelCall.id.asc())
        .all()
    )
    calls_by_post_id: dict[int, list[ModelCall]] = {}
    for call in model_calls:
        calls_by_post_id.setdefault(call.post_id, []).append(call)
    return calls_by_post_id


def _user_feed_maps() -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    user_feed_map: dict[int, list[int]] = {}
    feed_user_map: dict[int, list[int]] = {}
    for uf in UserFeed.query.all():
        user_feed_map.setdefault(uf.user_id, []).append(uf.feed_id)
        feed_user_map.setdefault(uf.feed_id, []).append(uf.user_id)
    return user_feed_map, feed_user_map


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

    config_data = read_combined()
    app_config = config_data.get("app", {})
    # Effective tier: runtime config already has environment overrides applied.
    llm_service_tier = (
        getattr(runtime_config, "llm_service_tier", None) or DEFAULTS.LLM_SERVICE_TIER
    )

    legacy_cost_rate = float(
        app_config.get("cost_rate_per_hour", DEFAULTS.APP_COST_RATE_PER_HOUR) or 0.0
    )
    whisper_cost_rate = float(
        app_config.get(
            "whisper_cost_rate_per_hour", DEFAULTS.APP_WHISPER_COST_RATE_PER_HOUR
        )
        or 0.0
    )

    # --- Users ---
    users: list[User] = User.query.order_by(User.username).all()

    # --- Feeds and subscriber counts ---
    feeds: list[Feed] = Feed.query.all()
    feed_subscriber_count: dict[int, int] = {}
    for feed in feeds:
        feed_subscriber_count[feed.id] = len(feed.user_feeds)

    # Fetch posts for these guids
    job_by_guid = _latest_completed_jobs_by_guid(month_start, month_end)
    guids = list(job_by_guid.keys())
    posts_in_month: list[Post] = (
        Post.query.filter(Post.guid.in_(guids)).all() if guids else []
    )
    post_map: dict[str, Post] = {p.guid: p for p in posts_in_month}

    # post.duration is the processed (ad-removed) length. The transcript is of
    # the unprocessed audio, so its last segment end is a lower bound on the
    # original length that does not depend on which ad labels were cut; it misses
    # any untranscribed tail after the last segment.
    post_ids = [p.id for p in posts_in_month]
    transcript_end_by_post_id = _transcript_end_by_post_id(post_ids)
    model_calls_by_post_id = _model_calls_by_post_id(post_ids)

    # --- Per-user monthly cost breakdown ---
    user_feed_map, feed_user_map = _user_feed_maps()

    # For each completed post this month, attribute cost to each subscriber
    user_costs: dict[int, float] = {u.id: 0.0 for u in users}
    feed_costs: dict[int, float] = {f.id: 0.0 for f in feeds}
    feed_llm_costs: dict[int, float] = {f.id: 0.0 for f in feeds}
    llm_cost_by_tier: dict[str, float] = {}
    feed_whisper_costs: dict[int, float] = {f.id: 0.0 for f in feeds}
    feed_episode_counts: dict[int, int] = {f.id: 0 for f in feeds}
    total_audio_hours = 0.0

    for guid, _job in job_by_guid.items():
        post = post_map.get(guid)
        if not post:
            continue
        duration = max(
            float(post.duration or 0), transcript_end_by_post_id.get(post.id, 0.0)
        )
        feed_id = post.feed_id
        subscriber_count = feed_subscriber_count.get(feed_id, 0)
        duration_hours = duration / 3600.0 if duration > 0 else 0.0
        total_audio_hours += duration_hours
        post_model_calls = model_calls_by_post_id.get(post.id, [])
        llm_cost = 0.0
        for call in post_model_calls:
            if not _is_billable_llm_call(call):
                continue
            call_cost = _persisted_or_computed_cost(call)
            tier = (call.service_tier or "default").lower()
            llm_cost += call_cost
            llm_cost_by_tier[tier] = llm_cost_by_tier.get(tier, 0.0) + call_cost
        whisper_cost = (
            whisper_cost_rate * duration_hours
            if any(_is_whisper_call(call) for call in post_model_calls)
            else 0.0
        )
        total_episode_cost = llm_cost + whisper_cost
        cost_per_sub = _compute_cost_per_subscriber(
            total_episode_cost, subscriber_count
        )

        feed_costs[feed_id] = feed_costs.get(feed_id, 0.0) + total_episode_cost
        feed_llm_costs[feed_id] = feed_llm_costs.get(feed_id, 0.0) + llm_cost
        feed_whisper_costs[feed_id] = (
            feed_whisper_costs.get(feed_id, 0.0) + whisper_cost
        )
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
                "llm_cost": round(feed_llm_costs.get(feed.id, 0.0), 4),
                "whisper_cost": round(feed_whisper_costs.get(feed.id, 0.0), 4),
            }
        )
    feeds_data.sort(key=lambda f: f["monthly_cost"], reverse=True)

    total_cost = round(sum(feed_costs.values()), 4)

    return jsonify(
        {
            "year": year,
            "month": month,
            "total_cost": total_cost,
            "cost_rate_per_hour": legacy_cost_rate,
            "whisper_cost_rate_per_hour": whisper_cost_rate,
            "total_llm_cost": round(sum(feed_llm_costs.values()), 4),
            "llm_service_tier": llm_service_tier,
            "llm_cost_by_tier": {
                tier: round(cost, 4) for tier, cost in sorted(llm_cost_by_tier.items())
            },
            "total_whisper_cost": round(sum(feed_whisper_costs.values()), 4),
            "total_audio_hours": round(total_audio_hours, 2),
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
            "service_tier": c.service_tier,
            "prompt_tokens": c.prompt_tokens,
            "cached_prompt_tokens": c.cached_prompt_tokens,
            "completion_tokens": c.completion_tokens,
            "total_tokens": c.total_tokens,
            # Same rule as the dashboard: the stored cost, or one priced from
            # tokens for legacy rows without a usable one.
            "estimated_cost": (
                round(_persisted_or_computed_cost(c), 8)
                if _is_billable_llm_call(c)
                else 0.0
            ),
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


@costs_bp.route("/api/admin/costs/backfill-estimated-cost", methods=["POST"])
def api_admin_backfill_estimated_cost() -> flask.Response:
    """Populate ``ModelCall.estimated_cost_usd`` for legacy rows.

    New ModelCalls are priced when the processing worker finalizes them. Rows
    that predate the column have ``estimated_cost_usd IS NULL``; this endpoint
    prices them from their stored token usage and writes the value back via
    the writer. Rows without token usage stay NULL so running the token
    backfill afterwards can still price them.

    POST body (all optional):
      apply: bool (default False — dry run when false)
      limit: int  (optional cap on rows to touch)
    """
    _, error_response = require_admin("backfill estimated cost")
    if error_response:
        return error_response

    payload = request.get_json(silent=True) or {}
    apply = bool(payload.get("apply", False))
    limit_raw = payload.get("limit")
    limit: int | None = None
    if limit_raw not in (None, ""):
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return flask.make_response(jsonify({"error": "Invalid limit"}), 400)
        if limit <= 0:
            return flask.make_response(jsonify({"error": "Invalid limit"}), 400)

    query = ModelCall.query.filter(
        ModelCall.estimated_cost_usd.is_(None),
        ModelCall.status.like("success%"),
    ).order_by(ModelCall.id.asc())
    # The cap counts rows that change, not rows looked at: unpriceable rows stay
    # NULL, so a plain LIMIT would revisit the same ones on every run.
    scanned = 0
    eligible = 0
    updated = 0
    skipped_non_billable = 0
    skipped_no_tokens = 0
    failed_updates = 0
    changed = 0
    for call in query.yield_per(200):
        if limit and changed >= limit:
            break
        scanned += 1
        if not _is_billable_llm_call(call):
            skipped_non_billable += 1
            cost = 0.0
        elif not (
            call.prompt_tokens or call.cached_prompt_tokens or call.completion_tokens
        ):
            skipped_no_tokens += 1
            continue
        else:
            eligible += 1
            cost = round(_model_call_cost(call), 8)
        changed += 1
        if not apply:
            continue
        result = writer_client.update(
            "ModelCall",
            int(call.id),
            {"estimated_cost_usd": cost},
            wait=True,
        )
        if result and result.success:
            updated += 1
        else:
            failed_updates += 1

    return jsonify(
        {
            "scanned": scanned,
            "eligible": eligible,
            "skipped_non_billable": skipped_non_billable,
            "skipped_no_tokens": skipped_no_tokens,
            "updated": updated,
            "failed_updates": failed_updates,
            "applied": apply,
        }
    )


@costs_bp.route("/api/admin/costs/backfill-token-usage", methods=["POST"])
def api_admin_backfill_token_usage() -> flask.Response:
    """Estimate missing token usage for legacy LLM ModelCall rows."""
    _, error_response = require_admin("backfill token usage")
    if error_response:
        return error_response

    payload = request.get_json(silent=True) or {}
    apply_backfill = bool(payload.get("apply", False))
    limit_raw = payload.get("limit")
    limit = None
    if limit_raw not in (None, ""):
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            return flask.make_response(jsonify({"error": "Invalid limit"}), 400)
        if limit <= 0:
            return flask.make_response(jsonify({"error": "Invalid limit"}), 400)

    result = backfill_model_call_token_usage(apply=apply_backfill, limit=limit)
    return jsonify(result)


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
