"""Routes for managing prompt presets and viewing processing statistics."""

from flask import Blueprint, current_app, g, jsonify, make_response, request
from sqlalchemy import func

from app.extensions import db
from app.models import Post, ProcessingStatistics, PromptPreset, User, UserDownload, UserFeedSubscription

preset_bp = Blueprint("preset", __name__, url_prefix="/api/presets")


def _require_admin():
    """Check if the current user is an admin. Returns error response if not."""
    settings = current_app.config.get("AUTH_SETTINGS")
    # When REQUIRE_AUTH=false we intentionally allow these routes.
    if not settings or not settings.require_auth:
        return None

    current = getattr(g, "current_user", None)
    if current is None:
        return make_response(jsonify({"error": "Authentication required."}), 401)

    user = User.query.get(current.id)
    if user is None or user.role != "admin":
        return make_response(jsonify({"error": "Admin privileges required."}), 403)

    return None


@preset_bp.route("", methods=["GET"])
def list_presets():
    """List all available prompt presets."""
    # Define correct order: conservative -> balanced -> aggressive -> maximum
    aggressiveness_order = {"conservative": 1, "balanced": 2, "aggressive": 3, "maximum": 4}
    presets = PromptPreset.query.all()
    presets.sort(key=lambda p: aggressiveness_order.get(p.aggressiveness, 99))
    
    return jsonify(
        {
            "presets": [
                {
                    "id": preset.id,
                    "name": preset.name,
                    "description": preset.description,
                    "aggressiveness": preset.aggressiveness,
                    "min_confidence": preset.min_confidence,
                    "is_active": preset.is_active,
                    "is_default": preset.is_default,
                    "system_prompt": preset.system_prompt,
                    "user_prompt_template": preset.user_prompt_template,
                    "created_at": preset.created_at.isoformat(),
                    "updated_at": preset.updated_at.isoformat(),
                }
                for preset in presets
            ]
        }
    )


@preset_bp.route("/<int:preset_id>", methods=["GET"])
def get_preset(preset_id: int):
    """Get details of a specific preset including prompts."""
    preset = PromptPreset.query.get_or_404(preset_id)
    
    return jsonify(
        {
            "id": preset.id,
            "name": preset.name,
            "description": preset.description,
            "aggressiveness": preset.aggressiveness,
            "system_prompt": preset.system_prompt,
            "user_prompt_template": preset.user_prompt_template,
            "min_confidence": preset.min_confidence,
            "is_active": preset.is_active,
            "is_default": preset.is_default,
            "created_at": preset.created_at.isoformat(),
            "updated_at": preset.updated_at.isoformat(),
        }
    )


@preset_bp.route("/<int:preset_id>/activate", methods=["POST"])
def activate_preset(preset_id: int):
    """Activate a specific preset (deactivates all others) and update output settings."""
    error_response = _require_admin()
    if error_response:
        return error_response
    
    from app.models import OutputSettings
    
    preset = PromptPreset.query.get_or_404(preset_id)
    
    # Deactivate all presets
    PromptPreset.query.update({"is_active": False})
    
    # Activate the selected preset
    preset.is_active = True
    
    # Also update the output settings min_confidence to match the preset
    output_settings = OutputSettings.query.first()
    if output_settings:
        output_settings.min_confidence = preset.min_confidence
    
    db.session.commit()
    
    return jsonify(
        {
            "message": f"Preset '{preset.name}' activated successfully",
            "preset": {
                "id": preset.id,
                "name": preset.name,
                "aggressiveness": preset.aggressiveness,
                "is_active": preset.is_active,
                "min_confidence": preset.min_confidence,
            },
        }
    )


@preset_bp.route("", methods=["POST"])
def create_preset():
    """Create a new custom prompt preset."""
    error_response = _require_admin()
    if error_response:
        return error_response
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = [
        "name",
        "aggressiveness",
        "system_prompt",
        "user_prompt_template",
    ]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Check if name already exists
    existing = PromptPreset.query.filter_by(name=data["name"]).first()
    if existing:
        return jsonify({"error": f"Preset with name '{data['name']}' already exists"}), 409
    
    # Create new preset
    preset = PromptPreset(
        name=data["name"],
        description=data.get("description"),
        aggressiveness=data["aggressiveness"],
        system_prompt=data["system_prompt"],
        user_prompt_template=data["user_prompt_template"],
        min_confidence=data.get("min_confidence", 0.7),
        is_active=False,  # Don't auto-activate custom presets
        is_default=False,
    )
    
    db.session.add(preset)
    db.session.commit()
    
    return (
        jsonify(
            {
                "message": "Preset created successfully",
                "preset": {
                    "id": preset.id,
                    "name": preset.name,
                    "aggressiveness": preset.aggressiveness,
                },
            }
        ),
        201,
    )


@preset_bp.route("/<int:preset_id>", methods=["PUT"])
def update_preset(preset_id: int):
    """Update an existing preset."""
    error_response = _require_admin()
    if error_response:
        return error_response
    
    preset = PromptPreset.query.get_or_404(preset_id)
    data = request.get_json()
    
    # Update fields if provided
    if "name" in data:
        # Check if new name conflicts with existing preset
        existing = PromptPreset.query.filter(
            PromptPreset.name == data["name"], PromptPreset.id != preset_id
        ).first()
        if existing:
            return jsonify({"error": f"Preset with name '{data['name']}' already exists"}), 409
        preset.name = data["name"]
    
    if "description" in data:
        preset.description = data["description"]
    if "aggressiveness" in data:
        preset.aggressiveness = data["aggressiveness"]
    if "system_prompt" in data:
        preset.system_prompt = data["system_prompt"]
    if "user_prompt_template" in data:
        preset.user_prompt_template = data["user_prompt_template"]
    if "min_confidence" in data:
        preset.min_confidence = data["min_confidence"]
    
    db.session.commit()
    
    return jsonify(
        {
            "message": "Preset updated successfully",
            "preset": {
                "id": preset.id,
                "name": preset.name,
                "aggressiveness": preset.aggressiveness,
            },
        }
    )


@preset_bp.route("/<int:preset_id>", methods=["DELETE"])
def delete_preset(preset_id: int):
    """Delete a custom preset (cannot delete default presets)."""
    error_response = _require_admin()
    if error_response:
        return error_response
    
    preset = PromptPreset.query.get_or_404(preset_id)
    
    if preset.is_default:
        return jsonify({"error": "Cannot delete default presets"}), 403
    
    if preset.is_active:
        return jsonify(
            {"error": "Cannot delete active preset. Please activate another preset first."}
        ), 403
    
    db.session.delete(preset)
    db.session.commit()
    
    return jsonify({"message": f"Preset '{preset.name}' deleted successfully"})


# Statistics routes
stats_bp = Blueprint("stats", __name__, url_prefix="/api/statistics")


def _get_current_user() -> User | None:
    """Get the current authenticated user, if any."""
    settings = current_app.config.get("AUTH_SETTINGS")
    if not settings or not settings.require_auth:
        return None
    current = getattr(g, "current_user", None)
    if current is None:
        return None
    return User.query.get(current.id)


def _is_admin_user(user: User | None) -> bool:
    """Check if the user is an admin."""
    return user is not None and user.role == "admin"


@stats_bp.route("/summary", methods=["GET"])
def get_summary_statistics():
    """Get statistics - server-wide for admins, user-specific for regular users."""
    current_user = _get_current_user()
    is_admin = _is_admin_user(current_user)

    scope = request.args.get("scope")
    force_user_scope = scope == "user"
    force_global_scope = scope == "global"

    if current_user is None:
        # No auth context: show server-wide stats
        total_stats = db.session.query(
            func.count(ProcessingStatistics.id).label("total_episodes"),
            func.sum(ProcessingStatistics.total_ad_segments_removed).label(
                "total_segments_removed"
            ),
            func.sum(ProcessingStatistics.total_duration_removed_seconds).label(
                "total_time_saved_seconds"
            ),
            func.avg(ProcessingStatistics.percentage_removed).label("avg_percentage_removed"),
        ).first()
    elif (is_admin and not force_user_scope) or (force_global_scope and is_admin):
        # Admin (default) or explicit global scope: show server-wide stats
        total_stats = db.session.query(
            func.count(ProcessingStatistics.id).label("total_episodes"),
            func.sum(ProcessingStatistics.total_ad_segments_removed).label(
                "total_segments_removed"
            ),
            func.sum(ProcessingStatistics.total_duration_removed_seconds).label(
                "total_time_saved_seconds"
            ),
            func.avg(ProcessingStatistics.percentage_removed).label("avg_percentage_removed"),
        ).first()
    else:
        # Regular user: show stats for episodes they've downloaded
        downloaded_post_ids = (
            db.session.query(UserDownload.post_id)
            .filter(UserDownload.user_id == current_user.id)
            .filter(UserDownload.is_processed.is_(True))
            .distinct()
            .subquery()
        )
        total_stats = db.session.query(
            func.count(ProcessingStatistics.id).label("total_episodes"),
            func.sum(ProcessingStatistics.total_ad_segments_removed).label(
                "total_segments_removed"
            ),
            func.sum(ProcessingStatistics.total_duration_removed_seconds).label(
                "total_time_saved_seconds"
            ),
            func.avg(ProcessingStatistics.percentage_removed).label("avg_percentage_removed"),
        ).filter(ProcessingStatistics.post_id.in_(downloaded_post_ids)).first()

    # Convert time saved to hours and minutes
    total_time_saved_seconds = total_stats.total_time_saved_seconds or 0
    hours = int(total_time_saved_seconds // 3600)
    minutes = int((total_time_saved_seconds % 3600) // 60)

    return jsonify(
        {
            "total_episodes_processed": total_stats.total_episodes or 0,
            "total_ad_segments_removed": int(total_stats.total_segments_removed or 0),
            "total_time_saved_seconds": round(total_time_saved_seconds, 1),
            "total_time_saved_formatted": f"{hours}h {minutes}m",
            "average_percentage_removed": round(total_stats.avg_percentage_removed or 0, 2),
            "is_user_specific": current_user is not None and (force_user_scope or not is_admin),
        }
    )


@stats_bp.route("/episodes", methods=["GET"])
def get_episode_statistics():
    """Get statistics for individual episodes with pagination."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    feed_id = request.args.get("feed_id", type=int)
    
    # Build query
    query = (
        db.session.query(ProcessingStatistics, Post)
        .join(Post, ProcessingStatistics.post_id == Post.id)
        .order_by(ProcessingStatistics.created_at.desc())
    )
    
    # Filter by feed if specified
    if feed_id:
        query = query.filter(Post.feed_id == feed_id)
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    episodes = []
    for stat, post in pagination.items:
        episodes.append(
            {
                "post_id": post.id,
                "post_title": post.title,
                "feed_id": post.feed_id,
                "release_date": post.release_date.isoformat() if post.release_date else None,
                "statistics": {
                    "segments_removed": stat.total_ad_segments_removed,
                    "duration_removed_seconds": round(stat.total_duration_removed_seconds, 1),
                    "duration_removed_formatted": _format_duration(
                        stat.total_duration_removed_seconds
                    ),
                    "original_duration_seconds": round(stat.original_duration_seconds, 1),
                    "processed_duration_seconds": round(stat.processed_duration_seconds, 1),
                    "percentage_removed": round(stat.percentage_removed, 2),
                    "processed_at": stat.created_at.isoformat(),
                },
            }
        )
    
    return jsonify(
        {
            "episodes": episodes,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }
    )


@stats_bp.route("/episodes/<int:post_id>", methods=["GET"])
def get_episode_statistics_detail(post_id: int):
    """Get detailed statistics for a specific episode."""
    stat = ProcessingStatistics.query.filter_by(post_id=post_id).first_or_404()
    post = Post.query.get_or_404(post_id)
    
    preset = None
    if stat.prompt_preset_id:
        preset_obj = PromptPreset.query.get(stat.prompt_preset_id)
        if preset_obj:
            preset = {
                "id": preset_obj.id,
                "name": preset_obj.name,
                "aggressiveness": preset_obj.aggressiveness,
            }
    
    return jsonify(
        {
            "post": {
                "id": post.id,
                "title": post.title,
                "feed_id": post.feed_id,
                "release_date": post.release_date.isoformat() if post.release_date else None,
            },
            "statistics": {
                "segments_removed": stat.total_ad_segments_removed,
                "duration_removed_seconds": round(stat.total_duration_removed_seconds, 1),
                "duration_removed_formatted": _format_duration(
                    stat.total_duration_removed_seconds
                ),
                "original_duration_seconds": round(stat.original_duration_seconds, 1),
                "original_duration_formatted": _format_duration(stat.original_duration_seconds),
                "processed_duration_seconds": round(stat.processed_duration_seconds, 1),
                "processed_duration_formatted": _format_duration(
                    stat.processed_duration_seconds
                ),
                "percentage_removed": round(stat.percentage_removed, 2),
                "processed_at": stat.created_at.isoformat(),
                "prompt_preset": preset,
            },
        }
    )


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"
