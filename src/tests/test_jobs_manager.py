from __future__ import annotations

from pathlib import Path

import app.jobs_manager as jobs_manager_module
from app.extensions import db
from app.jobs_manager import JobsManager
from app.models import Feed, Post


def _create_feed() -> Feed:
    feed = Feed(
        title="Test Feed",
        rss_url="https://example.com/feed.xml",
    )
    db.session.add(feed)
    db.session.commit()
    return feed


def _create_post(
    *,
    feed_id: int,
    guid: str,
    download_url: str,
    whitelisted: bool,
    processed_audio_path: str | None,
) -> Post:
    post = Post(
        feed_id=feed_id,
        guid=guid,
        download_url=download_url,
        title=guid,
        whitelisted=whitelisted,
        processed_audio_path=processed_audio_path,
    )
    db.session.add(post)
    db.session.commit()
    return post


def test_ensure_jobs_skips_whitelisted_posts_with_existing_processed_audio(
    app, monkeypatch, tmp_path: Path
) -> None:
    feed = _create_feed()

    processed_file = tmp_path / "processed.mp3"
    processed_file.write_bytes(b"test")

    processed_post = _create_post(
        feed_id=feed.id,
        guid="processed-guid",
        download_url="https://example.com/processed.mp3",
        whitelisted=True,
        processed_audio_path=str(processed_file),
    )
    unprocessed_post = _create_post(
        feed_id=feed.id,
        guid="unprocessed-guid",
        download_url="https://example.com/unprocessed.mp3",
        whitelisted=True,
        processed_audio_path=None,
    )
    _create_post(
        feed_id=feed.id,
        guid="not-whitelisted-guid",
        download_url="https://example.com/not-whitelisted.mp3",
        whitelisted=False,
        processed_audio_path=None,
    )

    created_guids: list[str] = []

    class FakeSingleJobManager:
        def __init__(self, post_guid: str, *_args, **_kwargs) -> None:
            self.post_guid = post_guid

        def ensure_job(self) -> None:
            created_guids.append(self.post_guid)

    monkeypatch.setattr(jobs_manager_module, "SingleJobManager", FakeSingleJobManager)

    manager = JobsManager.__new__(JobsManager)
    manager._status_manager = object()
    created = manager._ensure_jobs_for_all_posts("run-id")

    assert created == 1
    assert created_guids == [unprocessed_post.guid]
    assert processed_post.guid not in created_guids


def test_ensure_jobs_creates_job_when_processed_path_is_missing_file(
    app, monkeypatch, tmp_path: Path
) -> None:
    feed = _create_feed()

    missing_processed_path = tmp_path / "missing.mp3"
    post = _create_post(
        feed_id=feed.id,
        guid="missing-file-guid",
        download_url="https://example.com/missing-file.mp3",
        whitelisted=True,
        processed_audio_path=str(missing_processed_path),
    )

    created_guids: list[str] = []

    class FakeSingleJobManager:
        def __init__(self, post_guid: str, *_args, **_kwargs) -> None:
            self.post_guid = post_guid

        def ensure_job(self) -> None:
            created_guids.append(self.post_guid)

    monkeypatch.setattr(jobs_manager_module, "SingleJobManager", FakeSingleJobManager)

    manager = JobsManager.__new__(JobsManager)
    manager._status_manager = object()
    created = manager._ensure_jobs_for_all_posts("run-id")

    assert created == 1
    assert created_guids == [post.guid]
