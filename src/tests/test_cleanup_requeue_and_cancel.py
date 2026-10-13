from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect

from app.extensions import db
from app.models import Feed, Post, ProcessingJob
from app.writer.actions.cleanup import cleanup_missing_audio_paths_action
from app.writer.actions.jobs import mark_cancelled_action


def _create_feed_and_post(app, *, guid="test-guid", audio_path="/tmp/nonexistent.mp3"):
    feed = Feed(
        title="Test Feed",
        description="desc",
        author="author",
        rss_url="https://example.com/feed.xml",
    )
    db.session.add(feed)
    db.session.commit()

    post = Post(
        guid=guid,
        title="Test Episode",
        download_url="https://example.com/ep.mp3",
        feed_id=feed.id,
        whitelisted=True,
        unprocessed_audio_path=audio_path,
    )
    db.session.add(post)
    db.session.commit()
    return feed, post


class TestCleanupRequeuesWhenAudioMissing:
    """Whitelisted posts with missing audio should be re-queued for reprocessing
    regardless of previous job status (except pending/running which are already active)."""

    def test_completed_job_requeued(self, app):
        with app.app_context():
            _, post = _create_feed_and_post(app)
            job = ProcessingJob(
                post_guid=post.guid,
                status="completed",
                completed_at=datetime.now(UTC).replace(tzinfo=None),
            )
            db.session.add(job)
            db.session.commit()

            cleanup_missing_audio_paths_action({})
            db.session.commit()
            db.session.refresh(job)

            assert job.status == "pending"
            assert job.step_name == "Not started"

    def test_failed_job_requeued(self, app):
        with app.app_context():
            _, post = _create_feed_and_post(app, guid="failed-guid")
            job = ProcessingJob(
                post_guid=post.guid,
                status="failed",
                error_message="some error",
                completed_at=datetime.now(UTC).replace(tzinfo=None),
            )
            db.session.add(job)
            db.session.commit()

            cleanup_missing_audio_paths_action({})
            db.session.commit()
            db.session.refresh(job)

            assert job.status == "pending"
            assert job.error_message is None
            assert job.step_name == "Not started"

    def test_pending_job_not_reset(self, app):
        with app.app_context():
            _, post = _create_feed_and_post(app, guid="pending-guid")
            job = ProcessingJob(
                post_guid=post.guid,
                status="pending",
                step_name="Queued",
            )
            db.session.add(job)
            db.session.commit()

            cleanup_missing_audio_paths_action({})
            db.session.commit()
            db.session.refresh(job)

            assert job.status == "pending"
            assert job.step_name == "Queued"


class TestMarkCancelledAction:
    def test_sets_step_name(self, app):
        with app.app_context():
            job = ProcessingJob(post_guid="cancel-test", status="running")
            db.session.add(job)
            db.session.commit()

            mark_cancelled_action({"job_id": job.id, "reason": "Duplicate episode"})
            db.session.commit()
            db.session.refresh(job)

            assert job.status == "cancelled"
            assert job.step_name == "Duplicate episode"
            assert job.error_message == "Duplicate episode"

    def test_default_reason_when_none(self, app):
        with app.app_context():
            job = ProcessingJob(post_guid="cancel-default", status="running")
            db.session.add(job)
            db.session.commit()

            mark_cancelled_action({"job_id": job.id})
            db.session.commit()
            db.session.refresh(job)

            assert job.status == "cancelled"
            assert job.step_name == "Cancelled by user request"
            assert job.error_message == "Cancelled by user request"


def test_cleanup_query_count_does_not_grow_with_changed_posts(app, tmp_path):
    existing = tmp_path / "existing.mp3"
    existing.write_bytes(b"audio")
    missing = str(tmp_path / "missing.mp3")
    feeds = [
        Feed(title=f"Feed {i}", rss_url=f"https://example.com/{i}.xml")
        for i in range(3)
    ]
    db.session.add_all(feeds)
    db.session.flush()
    for i, feed in enumerate(feeds):
        db.session.add(
            Post(
                feed_id=feed.id,
                guid=f"missing-{i}",
                title=f"Missing {i}",
                download_url=f"https://example.com/missing-{i}.mp3",
                whitelisted=True,
                unprocessed_audio_path=missing,
                processed_audio_path=missing,
            )
        )
        db.session.add(
            ProcessingJob(
                post_guid=f"missing-{i}", status="completed", step_name="Done"
            )
        )
    db.session.add_all(
        [
            Post(
                feed_id=feeds[0].id,
                guid="existing",
                title="Existing",
                download_url="https://example.com/existing.mp3",
                whitelisted=True,
                unprocessed_audio_path=str(existing),
                processed_audio_path=str(existing),
            ),
            Post(
                feed_id=feeds[1].id,
                guid="ignored",
                title="Ignored",
                download_url="https://example.com/ignored.mp3",
                whitelisted=False,
                unprocessed_audio_path=missing,
            ),
        ]
    )
    db.session.commit()
    engine = db.engine
    db.session.remove()

    selects = []
    loaded_feeds = []
    unloaded_post_columns = []

    def capture_sql(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("select"):
            selects.append(statement)

    def capture_feed(feed, context):
        loaded_feeds.append(feed.id)

    def capture_post(post, context):
        unloaded_post_columns.append(sa_inspect(post).unloaded)

    event.listen(engine, "before_cursor_execute", capture_sql)
    event.listen(Feed, "load", capture_feed)
    event.listen(Post, "load", capture_post)
    try:
        changed = cleanup_missing_audio_paths_action({})
        db.session.commit()
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)
        event.remove(Feed, "load", capture_feed)
        event.remove(Post, "load", capture_post)

    assert changed == 3
    # One posts-with-feed-titles query and one job query, regardless of post count.
    assert len(selects) == 2
    assert loaded_feeds == []
    assert unloaded_post_columns
    assert all(
        {"description", "chapter_data", "refined_ad_boundaries"} <= unloaded
        for unloaded in unloaded_post_columns
    )

    db.session.remove()
    for i in range(3):
        post = Post.query.filter_by(guid=f"missing-{i}").one()
        assert post.unprocessed_audio_path is None
        assert post.processed_audio_path is None
        job = ProcessingJob.query.filter_by(post_guid=f"missing-{i}").one()
        assert job.status == "pending"
        assert job.step_name == "Not started"
    existing_post = Post.query.filter_by(guid="existing").one()
    assert existing_post.processed_audio_path == str(existing)
    assert Post.query.filter_by(guid="ignored").one().unprocessed_audio_path == missing
