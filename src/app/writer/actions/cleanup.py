import logging
import os
from pathlib import Path
from typing import Any

from sqlalchemy.orm import load_only

from app.extensions import db
from app.jobs_manager_run_service import recalculate_run_counts
from app.model_call_utils import whisper_model_call_filter
from app.models import (
    Feed,
    Identification,
    ModelCall,
    Post,
    ProcessingJob,
    TranscriptSegment,
)
from shared.processing_paths import find_existing_processed_audio_path

logger = logging.getLogger("writer")


def cleanup_missing_audio_paths_action(params: dict[str, Any]) -> int:
    inconsistent_posts = (
        db.session.query(Post, Feed.title)
        .outerjoin(Feed, Feed.id == Post.feed_id)
        .options(
            load_only(
                Post.id,
                Post.guid,
                Post.title,
                Post.feed_id,
                Post.unprocessed_audio_path,
                Post.processed_audio_path,
            )
        )
        .filter(
            Post.whitelisted,
            (
                (Post.unprocessed_audio_path.isnot(None))
                | (Post.processed_audio_path.isnot(None))
            ),
        )
        .all()
    )

    changed_guids = []
    for post, feed_title in inconsistent_posts:
        changed = False
        existing_processed_path = find_existing_processed_audio_path(
            processed_audio_path=post.processed_audio_path,
            unprocessed_audio_path=post.unprocessed_audio_path,
            feed_title=feed_title,
            post_title=post.title,
        )
        if existing_processed_path:
            resolved_processed_path = str(existing_processed_path)
            if post.processed_audio_path != resolved_processed_path:
                post.processed_audio_path = resolved_processed_path
                changed = True
        elif post.processed_audio_path:
            post.processed_audio_path = None
            changed = True
        if post.unprocessed_audio_path and not os.path.exists(
            post.unprocessed_audio_path
        ):
            post.unprocessed_audio_path = None
            changed = True

        if changed:
            changed_guids.append(post.guid)

    if changed_guids:
        latest_jobs: dict[str, ProcessingJob] = {}
        for job in (
            ProcessingJob.query.filter(ProcessingJob.post_guid.in_(changed_guids))
            .order_by(ProcessingJob.created_at.desc())
            .all()
        ):
            latest_jobs.setdefault(job.post_guid, job)
        for latest_job in latest_jobs.values():
            if latest_job.status not in {"pending", "running"}:
                latest_job.status = "pending"
                latest_job.current_step = 0
                latest_job.progress_percentage = 0.0
                latest_job.step_name = "Not started"
                latest_job.error_message = None
                latest_job.started_at = None
                latest_job.completed_at = None

    return len(changed_guids)


def clear_post_processing_data_action(params: dict[str, Any]) -> dict[str, Any]:
    post_id = params.get("post_id")
    post = db.session.get(Post, post_id)
    if not post:
        raise ValueError(f"Post {post_id} not found")

    logger.info("[WRITER] clear_post_processing_data_action: post_id=%s", post_id)

    # Chunked deletes for segments and identifications
    while True:
        ids_batch = [
            row[0]
            for row in db.session.query(TranscriptSegment.id)
            .filter_by(post_id=post.id)
            .limit(500)
            .all()
        ]
        if not ids_batch:
            logger.debug(
                "[WRITER] clear_post_processing_data_action: no more segments for post_id=%s",
                post_id,
            )
            break

        db.session.query(Identification).filter(
            Identification.transcript_segment_id.in_(ids_batch)
        ).delete(synchronize_session=False)

        db.session.query(TranscriptSegment).filter(
            TranscriptSegment.id.in_(ids_batch)
        ).delete(synchronize_session=False)

    # Model calls
    db.session.query(ModelCall).filter_by(post_id=post.id).delete()

    # Processing jobs
    db.session.query(ProcessingJob).filter_by(post_guid=post.guid).delete()

    # Reset post fields
    post.unprocessed_audio_path = None
    post.processed_audio_path = None
    post.duration = None
    post.chapter_data = None
    post.refined_ad_boundaries = None
    post.refined_ad_boundaries_updated_at = None

    logger.info(
        "[WRITER] clear_post_processing_data_action: completed post_id=%s", post_id
    )

    return {"post_id": post.id}


def clear_post_processing_data_keep_transcript_action(
    params: dict[str, Any],
) -> dict[str, Any]:
    """Clear processing outputs/classification state but preserve transcript rows."""
    post_id = params.get("post_id")
    post = db.session.get(Post, post_id)
    if not post:
        raise ValueError(f"Post {post_id} not found")

    logger.info(
        "[WRITER] clear_post_processing_data_keep_transcript_action: post_id=%s",
        post_id,
    )

    # Remove identifications tied to this post's transcript segments, but keep the
    # transcript segments themselves so the next run can reuse Whisper output.
    total_identifications_deleted = 0
    last_transcript_segment_id = 0
    while True:
        ids_batch = [
            row[0]
            for row in db.session.query(TranscriptSegment.id)
            .filter(
                TranscriptSegment.post_id == post.id,
                TranscriptSegment.id > last_transcript_segment_id,
            )
            .order_by(TranscriptSegment.id.asc())
            .limit(500)
            .all()
        ]
        if not ids_batch:
            logger.debug(
                "[WRITER] clear_post_processing_data_keep_transcript_action: "
                "no transcript segments for post_id=%s",
                post_id,
            )
            break

        deleted = (
            db.session.query(Identification)
            .filter(Identification.transcript_segment_id.in_(ids_batch))
            .delete(synchronize_session=False)
        )
        total_identifications_deleted += int(deleted or 0)
        last_transcript_segment_id = int(ids_batch[-1])

    # Keep Whisper model calls so transcription can be reused; drop all others.
    non_whisper_model_calls_deleted = (
        db.session.query(ModelCall)
        .filter(ModelCall.post_id == post.id)
        .filter(~whisper_model_call_filter())
        .delete(synchronize_session=False)
    )

    # Processing jobs should be regenerated for the new run.
    db.session.query(ProcessingJob).filter_by(post_guid=post.guid).delete(
        synchronize_session=False
    )

    # Reset output and derived processing fields, but preserve transcript/model calls.
    post.unprocessed_audio_path = None
    post.processed_audio_path = None
    post.duration = None
    post.chapter_data = None
    post.refined_ad_boundaries = None
    post.refined_ad_boundaries_updated_at = None

    logger.info(
        "[WRITER] clear_post_processing_data_keep_transcript_action: completed "
        "post_id=%s identifications_deleted=%s non_whisper_model_calls_deleted=%s",
        post_id,
        total_identifications_deleted,
        int(non_whisper_model_calls_deleted or 0),
    )

    return {"post_id": post.id}


def cleanup_processed_post_action(params: dict[str, Any]) -> dict[str, Any]:
    post_id = params.get("post_id")
    if not post_id:
        raise ValueError("post_id is required")

    post = db.session.get(Post, int(post_id))
    if not post:
        raise ValueError(f"Post {post_id} not found")

    logger.info("[WRITER] cleanup_processed_post_action: post_id=%s", post_id)

    # Remove processing artifacts and dependent rows.
    clear_post_processing_data_action({"post_id": post.id})
    post.whitelisted = False

    recalculate_run_counts(db.session)

    logger.info("[WRITER] cleanup_processed_post_action: completed post_id=%s", post_id)

    return {"post_id": post.id}


def cleanup_processed_post_files_only_action(params: dict[str, Any]) -> dict[str, Any]:
    """Remove audio files but preserve processing metadata."""
    post_id = params.get("post_id")
    if not post_id:
        raise ValueError("post_id is required")
    post = db.session.get(Post, int(post_id))
    if not post:
        raise ValueError(f"Post {post_id} not found")

    logger.info(
        "[WRITER] cleanup_processed_post_files_only_action: post_id=%s", post_id
    )

    # Delete audio files (using same pattern as post_cleanup.py)
    for path_str in [post.unprocessed_audio_path, post.processed_audio_path]:
        if not path_str:
            continue
        try:
            file_path = Path(path_str)
        except Exception:  # noqa: BLE001
            logger.warning("[WRITER] Invalid path for post %s: %s", post.guid, path_str)
            continue
        if not file_path.exists():
            continue
        try:
            file_path.unlink()
            logger.info("[WRITER] Deleted file: %s", file_path)
        except OSError as exc:
            logger.warning("[WRITER] Unable to delete %s: %s", file_path, exc)

    # Clear file paths but preserve duration and other metadata
    post.unprocessed_audio_path = None
    post.processed_audio_path = None
    # Un-whitelist the post (prevents re-queuing for processing)
    post.whitelisted = False

    # DO NOT delete: ModelCall, ProcessingJob, TranscriptSegment, Identification
    # DO NOT null: post.duration

    logger.info(
        "[WRITER] cleanup_processed_post_files_only_action: completed post_id=%s",
        post_id,
    )

    return {"post_id": post.id}
