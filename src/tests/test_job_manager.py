from types import SimpleNamespace
from unittest import mock

from app.extensions import db
from app.job_manager import JobManager
from app.models import Feed, Post


def _create_feed(title: str = "Test Feed") -> Feed:
    feed = Feed(title=title, rss_url="https://example.com/feed.xml")
    db.session.add(feed)
    db.session.commit()
    return feed


def _create_post(
    *,
    feed_id: int,
    guid: str,
    title: str,
    download_url: str,
    whitelisted: bool = True,
    processed_audio_path: str | None = None,
    unprocessed_audio_path: str | None = None,
) -> Post:
    post = Post(
        feed_id=feed_id,
        guid=guid,
        title=title,
        download_url=download_url,
        whitelisted=whitelisted,
        processed_audio_path=processed_audio_path,
        unprocessed_audio_path=unprocessed_audio_path,
    )
    db.session.add(post)
    db.session.commit()
    return post


def test_load_and_validate_post_skips_when_processed_audio_exists_via_fallback(
    app, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("PODLY_PODCAST_DATA_DIR", str(tmp_path))

    feed = _create_feed("My Feed")
    unprocessed_name = "episode.mp3"
    resolved_processed = tmp_path / "srv" / "My_Feed" / unprocessed_name
    resolved_processed.parent.mkdir(parents=True, exist_ok=True)
    resolved_processed.write_bytes(b"audio")

    post = _create_post(
        feed_id=feed.id,
        guid="post-guid",
        title="Episode",
        download_url="https://example.com/episode.mp3",
        processed_audio_path=None,
        unprocessed_audio_path=str(
            tmp_path / "in" / "jobs" / "post-guid" / unprocessed_name
        ),
    )

    manager = JobManager(
        post.guid,
        status_manager=mock.MagicMock(),
        logger_obj=mock.MagicMock(),
        run_id=None,
    )
    skip_mock = mock.Mock(return_value=SimpleNamespace(id="job-1"))
    manager.skip = skip_mock  # type: ignore[method-assign]

    with mock.patch("app.job_manager.writer_client.update") as mock_update:
        mock_update.return_value = SimpleNamespace(success=True)
        loaded_post, early_result = manager._load_and_validate_post()

    assert loaded_post is None
    assert early_result is not None
    assert early_result["status"] == "skipped"
    assert early_result["job_id"] == "job-1"
    skip_mock.assert_called_once_with("Post already processed")
    mock_update.assert_called_once_with(
        "Post",
        post.id,
        {"processed_audio_path": str(resolved_processed)},
        wait=True,
    )


def test_load_and_validate_post_does_not_skip_when_db_path_is_stale(
    app, tmp_path
) -> None:
    feed = _create_feed("Another Feed")
    missing_path = tmp_path / "srv" / "Another_Feed" / "missing.mp3"
    post = _create_post(
        feed_id=feed.id,
        guid="stale-guid",
        title="Stale",
        download_url="https://example.com/stale.mp3",
        processed_audio_path=str(missing_path),
        unprocessed_audio_path=None,
    )

    manager = JobManager(
        post.guid,
        status_manager=mock.MagicMock(),
        logger_obj=mock.MagicMock(),
        run_id=None,
    )
    skip_mock = mock.Mock()
    manager.skip = skip_mock  # type: ignore[method-assign]

    with mock.patch("app.job_manager.writer_client.update") as mock_update:
        loaded_post, early_result = manager._load_and_validate_post()

    assert loaded_post is not None
    assert loaded_post.id == post.id
    assert early_result is None
    skip_mock.assert_not_called()
    mock_update.assert_not_called()
