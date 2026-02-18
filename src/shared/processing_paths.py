import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessingPaths:
    post_processed_audio_path: Path


def _sanitize_post_title_for_filename(post_title: str) -> str:
    """Match legacy filename sanitization used by downloader/output code."""
    return re.sub(r"[^a-zA-Z0-9\s]", "", post_title)


def _sanitize_feed_title_legacy(feed_title: str) -> str:
    """Legacy feed-directory sanitization (spaces preserved)."""
    return re.sub(r"[^a-zA-Z0-9\s]", "", feed_title)


def _sanitize_feed_title_modern(feed_title: str) -> str:
    """Modern feed-directory sanitization (underscore-separated)."""
    sanitized_feed_title = re.sub(r"[^a-zA-Z0-9\s_.-]", "", feed_title).strip()
    sanitized_feed_title = sanitized_feed_title.rstrip(".")
    return re.sub(r"\s+", "_", sanitized_feed_title)


def paths_from_unprocessed_path(
    unprocessed_path: str, feed_title: str
) -> ProcessingPaths:
    unprocessed_filename = Path(unprocessed_path).name
    sanitized_feed_title = _sanitize_feed_title_modern(feed_title)

    return ProcessingPaths(
        post_processed_audio_path=get_srv_root()
        / sanitized_feed_title
        / unprocessed_filename,
    )


def get_processed_audio_path_candidates(
    *,
    processed_audio_path: str | None,
    unprocessed_audio_path: str | None,
    feed_title: str | None,
    post_title: str | None,
) -> list[Path]:
    """Return candidate processed-audio paths from legacy and modern conventions."""
    candidates: list[Path] = []

    if processed_audio_path:
        candidates.append(Path(processed_audio_path))

    if unprocessed_audio_path and feed_title:
        derived = paths_from_unprocessed_path(unprocessed_audio_path, feed_title)
        candidates.append(derived.post_processed_audio_path)

    if feed_title and post_title:
        sanitized_post_title = _sanitize_post_title_for_filename(post_title)
        if sanitized_post_title:
            candidates.append(
                get_srv_root()
                / _sanitize_feed_title_legacy(feed_title)
                / f"{sanitized_post_title}.mp3"
            )
            candidates.append(
                get_srv_root()
                / _sanitize_feed_title_modern(feed_title)
                / f"{sanitized_post_title}.mp3"
            )

    deduped: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def find_existing_processed_audio_path(
    *,
    processed_audio_path: str | None,
    unprocessed_audio_path: str | None,
    feed_title: str | None,
    post_title: str | None,
) -> Path | None:
    """Return the first non-empty processed-audio file found across path variants."""
    candidates = get_processed_audio_path_candidates(
        processed_audio_path=processed_audio_path,
        unprocessed_audio_path=unprocessed_audio_path,
        feed_title=feed_title,
        post_title=post_title,
    )
    for candidate in candidates:
        try:
            if (
                candidate.exists()
                and candidate.is_file()
                and candidate.stat().st_size > 0
            ):
                return candidate
        except OSError:
            continue
    return None


def get_job_unprocessed_path(post_guid: str, job_id: str, post_title: str) -> Path:
    """Return a unique per-job path for the unprocessed audio file.

    Layout: in/jobs/{post_guid}/{job_id}/{sanitized_title}.mp3
    """
    # Keep same sanitization behavior used for download filenames
    sanitized_title = re.sub(r"[^a-zA-Z0-9\s]", "", post_title).strip()
    return get_in_root() / "jobs" / post_guid / job_id / f"{sanitized_title}.mp3"


# ---- New centralized data-root helpers ----


def get_instance_dir() -> Path:
    """Absolute instance directory inside the container.

    Defaults to /app/src/instance. Can be overridden via PODLY_INSTANCE_DIR for tests.
    """
    return Path(os.environ.get("PODLY_INSTANCE_DIR", "/app/src/instance"))


def get_base_podcast_data_dir() -> Path:
    """Root under which podcasts (in/srv) live, e.g., /app/src/instance/data."""
    return Path(
        os.environ.get("PODLY_PODCAST_DATA_DIR", str(get_instance_dir() / "data"))
    )


def get_in_root() -> Path:
    return get_base_podcast_data_dir() / "in"


def get_srv_root() -> Path:
    return get_base_podcast_data_dir() / "srv"
