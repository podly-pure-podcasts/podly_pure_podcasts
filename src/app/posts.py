import logging
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from app.models import Identification, ModelCall, Post, ProcessingJob, TranscriptSegment
from app.writer.client import writer_client
from podcast_processor.podcast_downloader import get_and_make_download_path

logger = logging.getLogger("global_logger")


def _collect_processed_paths(post: Post) -> list[Path]:
    """Collect all possible processed audio paths to check for a post."""
    import re

    from podcast_processor.podcast_downloader import sanitize_title
    from shared.processing_paths import get_srv_root, paths_from_unprocessed_path

    processed_paths_to_check: list[Path] = []

    # 1. Check database path first (most reliable if set)
    if post.processed_audio_path:
        processed_paths_to_check.append(Path(post.processed_audio_path))

    # 2. Compute path using paths_from_unprocessed_path (matches processor logic)
    if post.unprocessed_audio_path and post.feed and post.feed.title:
        processing_paths = paths_from_unprocessed_path(
            post.unprocessed_audio_path, post.feed.title
        )
        if processing_paths:
            processed_paths_to_check.append(processing_paths.post_processed_audio_path)

    # 3. Fallback: compute expected path from post/feed titles
    if post.feed and post.feed.title and post.title:
        safe_feed_title = sanitize_title(post.feed.title)
        safe_post_title = sanitize_title(post.title)
        processed_paths_to_check.append(
            get_srv_root() / safe_feed_title / f"{safe_post_title}.mp3"
        )

        # 4. Also check with underscore-style sanitization
        sanitized_feed_title = re.sub(r"[^a-zA-Z0-9\s_.-]", "", post.feed.title).strip()
        sanitized_feed_title = sanitized_feed_title.rstrip(".")
        sanitized_feed_title = re.sub(r"\s+", "_", sanitized_feed_title)
        processed_paths_to_check.append(
            get_srv_root() / sanitized_feed_title / f"{safe_post_title}.mp3"
        )

    return processed_paths_to_check


def _dedupe_and_find_existing(paths: list[Path]) -> tuple[list[Path], Path | None]:
    """Deduplicate paths and find the first existing one."""
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for p in paths:
        resolved = p.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_paths.append(resolved)

    existing_path: Path | None = None
    for p in unique_paths:
        if p.exists():
            existing_path = p
            break

    return unique_paths, existing_path


def _remove_file_if_exists(path: Path | None, file_type: str, post_id: int) -> None:
    """Remove a file if it exists and log the result."""
    if not path:
        logger.debug(f"{file_type} path is None for post {post_id}.")
        return

    if not path.exists():
        logger.debug(f"No {file_type} file to remove for post {post_id}.")
        return

    try:
        path.unlink()
        logger.info(f"Removed {file_type} file: {path}")
    except OSError as e:
        logger.error(f"Failed to remove {file_type} file {path}: {e}")


def remove_associated_files(post: Post) -> None:
    """
    Remove unprocessed and processed audio files associated with a post.
    Computes paths from post/feed metadata to ensure files are found even
    if database paths are already cleared.

    We check multiple possible locations for processed audio because the path
    calculation has varied over time and between different code paths.
    """
    try:
        # Collect and find processed audio path
        processed_paths = _collect_processed_paths(post)
        unique_paths, processed_abs_path = _dedupe_and_find_existing(processed_paths)

        # Compute expected unprocessed audio path
        unprocessed_abs_path: Path | None = None
        if post.title:
            unprocessed_path = get_and_make_download_path(post.title)
            if unprocessed_path:
                unprocessed_abs_path = Path(unprocessed_path).resolve()

        # Fallback: if we couldn't find a processed path, try using the stored path directly
        if processed_abs_path is None and post.processed_audio_path:
            processed_abs_path = Path(post.processed_audio_path).resolve()

        # Remove audio files
        _remove_file_if_exists(unprocessed_abs_path, "unprocessed audio", post.id)

        if processed_abs_path:
            _remove_file_if_exists(processed_abs_path, "processed audio", post.id)
        elif unique_paths:
            logger.debug(
                f"No processed audio file to remove for post {post.id}. "
                f"Checked paths: {[str(p) for p in unique_paths]}"
            )
        else:
            logger.debug(
                f"Could not determine processed audio path for post {post.id}."
            )

    except Exception as e:
        logger.error(
            f"Unexpected error in remove_associated_files for post {post.id}: {e}",
            exc_info=True,
        )


def clear_post_processing_data(post: Post) -> None:
    """
    Clear all processing data for a post including:
    - Audio files (unprocessed and processed)
    - Database entries (transcript segments, identifications, model calls, processing jobs)
    - Reset relevant post fields
    """
    try:
        logger.info(
            f"Starting to clear processing data for post: {post.title} (ID: {post.id})"
        )

        # Remove audio files first
        remove_associated_files(post)

        writer_client.action(
            "clear_post_processing_data", {"post_id": post.id}, wait=True
        )

        logger.info(
            f"Successfully cleared all processing data for post: {post.title} (ID: {post.id})"
        )

    except Exception as e:
        logger.error(
            f"Error clearing processing data for post {post.id}: {e}",
            exc_info=True,
        )
        raise PostException(f"Failed to clear processing data: {e!s}") from e


def clear_post_identifications_only(post: Post) -> None:
    """
    Clear only identifications and LLM model calls, preserving transcript segments.

    This is useful for reprocessing with a different ad detection strategy
    while reusing the existing transcription (saves time and Whisper API costs).

    Preserves:
    - Transcript segments (no re-transcription needed)
    - Whisper model call records
    - Existing processed audio as a timestamped backup file

    Clears:
    - Identification records
    - Non-Whisper model call records
    - Processing job records
    - Refined ad boundaries
    - processed_audio_path (so reprocess does not short-circuit)
    """
    try:
        logger.info(
            f"Clearing identifications only for post: {post.title} (ID: {post.id})"
        )

        archived_processed_audio = _archive_processed_audio_for_reprocess(post)

        result = writer_client.action(
            "clear_post_identifications_only", {"post_id": post.id}, wait=True
        )

        if result and result.success:
            segments_preserved = (result.data or {}).get("segments_preserved", 0)
            archived_path = (
                str(archived_processed_audio) if archived_processed_audio else "none"
            )
            logger.info(
                f"Cleared identifications for post {post.id}, "
                f"preserved {segments_preserved} transcript segments, "
                f"archived_processed_audio={archived_path}"
            )
        else:
            raise PostException(
                f"Writer action failed: {getattr(result, 'error', 'Unknown error')}"
            )

    except PostException:
        raise
    except Exception as e:
        logger.error(
            f"Error clearing identifications for post {post.id}: {e}",
            exc_info=True,
        )
        raise PostException(f"Failed to clear identifications: {str(e)}") from e


def snapshot_post_processing_data(
    post: Post,
    *,
    trigger: str,
    force_retranscribe: bool,
    requested_by_user_id: Optional[int],
) -> Optional[Path]:
    """Persist a pre-reprocess snapshot of post processing data to JSON."""
    from shared.processing_paths import get_base_podcast_data_dir

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = get_base_podcast_data_dir() / "reprocess_snapshots" / str(post.guid)
    snapshot_path = snapshot_dir / f"{timestamp}.json"

    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_payload = _build_post_processing_snapshot(
            post=post,
            trigger=trigger,
            force_retranscribe=force_retranscribe,
            requested_by_user_id=requested_by_user_id,
        )
        with snapshot_path.open("w", encoding="utf-8") as fh:
            json.dump(
                snapshot_payload,
                fh,
                indent=2,
                ensure_ascii=True,
                default=_json_default,
            )
        logger.info("Saved reprocess snapshot for post %s at %s", post.id, snapshot_path)
        return snapshot_path
    except Exception as exc:  # pylint: disable=broad-except
        logger.error(
            "Failed to save reprocess snapshot for post %s: %s",
            post.id,
            exc,
            exc_info=True,
        )
        return None


class PostException(Exception):
    pass


def _archive_processed_audio_for_reprocess(post: Post) -> Optional[Path]:
    """Archive the current processed audio so reprocess can regenerate output."""
    processed_paths = _collect_processed_paths(post)
    _, processed_audio_path = _dedupe_and_find_existing(processed_paths)
    if processed_audio_path is None:
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = processed_audio_path.with_name(
        f"{processed_audio_path.name}.reprocess-{timestamp}.bak"
    )
    collision_index = 1
    while backup_path.exists():
        backup_path = processed_audio_path.with_name(
            f"{processed_audio_path.name}.reprocess-{timestamp}-{collision_index}.bak"
        )
        collision_index += 1

    try:
        processed_audio_path.replace(backup_path)
        logger.info(
            "Archived existing processed audio for post %s: %s -> %s",
            post.id,
            processed_audio_path,
            backup_path,
        )
        return backup_path
    except OSError as move_error:
        logger.warning(
            "Failed to archive processed audio via move for post %s (%s); "
            "falling back to copy+delete",
            post.id,
            move_error,
        )

    try:
        shutil.copy2(processed_audio_path, backup_path)
        processed_audio_path.unlink()
        logger.info(
            "Archived existing processed audio for post %s using copy+delete: %s -> %s",
            post.id,
            processed_audio_path,
            backup_path,
        )
        return backup_path
    except OSError as copy_error:
        logger.warning(
            "Failed to archive processed audio for post %s (%s); "
            "attempting delete to unblock reprocess",
            post.id,
            copy_error,
        )

    try:
        processed_audio_path.unlink()
        logger.info(
            "Deleted existing processed audio for post %s to allow reprocess: %s",
            post.id,
            processed_audio_path,
        )
        return None
    except OSError as delete_error:
        raise PostException(
            f"Failed to remove existing processed audio before reprocess: {delete_error}"
        ) from delete_error


def _build_post_processing_snapshot(
    *,
    post: Post,
    trigger: str,
    force_retranscribe: bool,
    requested_by_user_id: Optional[int],
) -> dict[str, Any]:
    feed_title = getattr(getattr(post, "feed", None), "title", None)

    transcript_segments = (
        TranscriptSegment.query.filter_by(post_id=post.id)
        .order_by(TranscriptSegment.sequence_num.asc())
        .all()
    )
    model_calls = (
        ModelCall.query.filter_by(post_id=post.id)
        .order_by(ModelCall.timestamp.asc(), ModelCall.id.asc())
        .all()
    )
    identifications = (
        Identification.query.join(
            TranscriptSegment,
            Identification.transcript_segment_id == TranscriptSegment.id,
        )
        .filter(TranscriptSegment.post_id == post.id)
        .order_by(
            Identification.model_call_id.asc(),
            Identification.transcript_segment_id.asc(),
            Identification.id.asc(),
        )
        .all()
    )
    processing_jobs = (
        ProcessingJob.query.filter_by(post_guid=post.guid)
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )

    return {
        "snapshot_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "request": {
            "trigger": trigger,
            "force_retranscribe": bool(force_retranscribe),
            "requested_by_user_id": requested_by_user_id,
        },
        "post": {
            "id": post.id,
            "guid": post.guid,
            "title": post.title,
            "feed_id": post.feed_id,
            "feed_title": feed_title,
            "whitelisted": post.whitelisted,
            "duration": post.duration,
            "chapter_data": post.chapter_data,
            "refined_ad_boundaries": post.refined_ad_boundaries,
            "refined_ad_boundaries_updated_at": _iso_datetime(
                post.refined_ad_boundaries_updated_at
            ),
            "processed_audio": _path_metadata(post.processed_audio_path),
            "unprocessed_audio": _path_metadata(post.unprocessed_audio_path),
        },
        "counts": {
            "transcript_segments": len(transcript_segments),
            "model_calls": len(model_calls),
            "identifications": len(identifications),
            "processing_jobs": len(processing_jobs),
        },
        "transcript_segments": [
            {
                "id": seg.id,
                "sequence_num": seg.sequence_num,
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "text": seg.text,
            }
            for seg in transcript_segments
        ],
        "model_calls": [
            {
                "id": call.id,
                "post_id": call.post_id,
                "model_name": call.model_name,
                "status": call.status,
                "first_segment_sequence_num": call.first_segment_sequence_num,
                "last_segment_sequence_num": call.last_segment_sequence_num,
                "timestamp": _iso_datetime(call.timestamp),
                "prompt": call.prompt,
                "response": call.response,
                "error_message": call.error_message,
                "retry_attempts": call.retry_attempts,
            }
            for call in model_calls
        ],
        "identifications": [
            {
                "id": ident.id,
                "transcript_segment_id": ident.transcript_segment_id,
                "model_call_id": ident.model_call_id,
                "label": ident.label,
                "confidence": ident.confidence,
            }
            for ident in identifications
        ],
        "processing_jobs": [
            {
                "id": job.id,
                "post_guid": job.post_guid,
                "status": job.status,
                "current_step": job.current_step,
                "step_name": job.step_name,
                "total_steps": job.total_steps,
                "progress_percentage": job.progress_percentage,
                "error_message": job.error_message,
                "created_at": _iso_datetime(job.created_at),
                "started_at": _iso_datetime(job.started_at),
                "completed_at": _iso_datetime(job.completed_at),
                "requested_by_user_id": job.requested_by_user_id,
                "billing_user_id": job.billing_user_id,
            }
            for job in processing_jobs
        ],
    }


def _path_metadata(path_str: Optional[str]) -> dict[str, Any]:
    if not path_str:
        return {"path": None, "exists": False, "size_bytes": None}
    path_obj = Path(path_str)
    exists = path_obj.exists()
    size_bytes: Optional[int] = None
    if exists:
        try:
            size_bytes = path_obj.stat().st_size
        except OSError:
            size_bytes = None
    return {"path": str(path_obj), "exists": exists, "size_bytes": size_bytes}


def _iso_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
