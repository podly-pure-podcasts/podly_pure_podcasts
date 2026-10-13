from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import event

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


@pytest.fixture
def refresh_manager(app, monkeypatch):
    """JobsManager with a counted scheduler context and stubbed cleanup/enqueue."""
    calls = []

    @contextmanager
    def scheduler_context():
        with app.app_context():
            calls.append(("context", None))
            yield

    monkeypatch.setattr(
        jobs_manager_module, "_scheduler_app_context", scheduler_context
    )
    manager = JobsManager.__new__(JobsManager)
    monkeypatch.setattr(
        manager, "_cleanup_inconsistent_posts", lambda: calls.append(("cleanup", None))
    )

    def enqueue(trigger, context):
        calls.append(("enqueue", (trigger, context)))
        return {"status": "ok", "enqueued": 0}

    monkeypatch.setattr(manager, "enqueue_pending_jobs", enqueue)
    return manager, calls


def _create_feeds(count: int) -> list[int]:
    feeds = [
        Feed(title=f"Feed {i}", rss_url=f"https://example.com/{i}.xml")
        for i in range(count)
    ]
    db.session.add_all(feeds)
    db.session.commit()
    feed_ids = [feed.id for feed in feeds]
    db.session.remove()
    return feed_ids


def test_start_refresh_all_feeds_uses_short_sessions(refresh_manager, monkeypatch):
    manager, calls = refresh_manager
    feed_ids = _create_feeds(3)
    loaded_feeds = []

    def refresh(feed):
        # Earlier feeds and their episodes must not remain in this session.
        assert [
            obj for obj in db.session.identity_map.values() if obj is not feed
        ] == []
        db.session.add(
            Post(
                feed_id=feed.id,
                guid=f"feed-{feed.id}",
                title="Episode",
                download_url=f"https://example.com/{feed.id}.mp3",
            )
        )
        db.session.flush()
        calls.append(("refresh", feed.id))

    def record_feed_load(feed, context):
        loaded_feeds.append(feed.id)

    monkeypatch.setattr(jobs_manager_module, "refresh_feed", refresh)
    event.listen(Feed, "load", record_feed_load)
    try:
        result = manager.start_refresh_all_feeds(
            trigger="manual", context={"reason": "test"}
        )
    finally:
        event.remove(Feed, "load", record_feed_load)

    assert result == {"status": "ok", "enqueued": 0, "feeds_refreshed": 3}
    # The inventory reads IDs only; each feed is loaded once, by its refresh.
    assert loaded_feeds == feed_ids
    per_feed = [
        call for fid in feed_ids for call in (("context", None), ("refresh", fid))
    ]
    assert calls == [
        ("context", None),
        *per_feed,
        ("context", None),
        ("cleanup", None),
        ("enqueue", ("manual", {"reason": "test"})),
    ]


def test_refresh_skips_deleted_feed(refresh_manager, monkeypatch):
    manager, _calls = refresh_manager
    refreshed = []
    monkeypatch.setattr(
        jobs_manager_module, "refresh_feed", lambda feed: refreshed.append(feed.id)
    )
    assert manager._refresh_feed_by_id(99999) is False
    assert refreshed == []


def test_one_failing_feed_does_not_stop_the_refresh_pass(refresh_manager, monkeypatch):
    manager, calls = refresh_manager
    feed_ids = _create_feeds(3)
    refreshed = []

    def refresh(feed):
        if feed.id == feed_ids[0]:
            raise RuntimeError("Feed refresh failed")
        refreshed.append(feed.id)

    monkeypatch.setattr(jobs_manager_module, "refresh_feed", refresh)
    result = manager.start_refresh_all_feeds()

    assert refreshed == feed_ids[1:]
    assert result["feeds_refreshed"] == 2
    assert ("cleanup", None) in calls
    assert calls[-1][0] == "enqueue"
