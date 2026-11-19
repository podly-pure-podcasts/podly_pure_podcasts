from datetime import UTC, datetime

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect

from app.extensions import db
from app.models import Feed, ModelCall, Post, ProcessingJob
from app.writer.actions.cleanup import cleanup_missing_audio_paths_action
from app.writer.actions.jobs import (
    cancel_existing_jobs_action,
    mark_cancelled_action,
)
from app.writer.actions.processor import upsert_model_call_action


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


class TestCancelExistingJobsCleansOrphanedModelCalls:
    """When a new processing job supersedes an in-flight one, any non-terminal
    ModelCall rows for the post must be marked cancelled. Otherwise they
    stay `pending` forever (visible in the UI as orphans) and collide with
    the new run's upsert against the unique
    (post_id, first_seq, last_seq, model_name) index.

    Regression: see app.log around 14:48-14:52 -- ModelCall 2515 was left
    pending after a tier-retry-backoff worker was killed by a new job, then
    a later upsert hit IntegrityError on the same key.
    """

    def _create_post(self, guid: str) -> Post:
        feed = Feed(
            title="Cancel Cleanup Feed",
            rss_url=f"https://example.com/{guid}.xml",
        )
        db.session.add(feed)
        db.session.flush()
        post = Post(
            feed_id=feed.id,
            guid=guid,
            download_url=f"https://example.com/{guid}.mp3",
            title=guid,
        )
        db.session.add(post)
        db.session.commit()
        return post

    def test_cancels_pending_model_calls_for_post(self, app):
        with app.app_context():
            post = self._create_post("orphan-pending-guid")
            old_job = ProcessingJob(post_guid=post.guid, status="running")
            db.session.add(old_job)
            db.session.commit()

            stuck = ModelCall(
                post_id=post.id,
                first_segment_sequence_num=2339,
                last_segment_sequence_num=2363,
                model_name="gemini/gemini-3-flash-preview",
                prompt="word boundary refine",
                status="pending",
            )
            succeeded = ModelCall(
                post_id=post.id,
                first_segment_sequence_num=0,
                last_segment_sequence_num=2363,
                model_name="gemini/gemini-3-flash-preview",
                prompt="classify",
                status="success",
                response="{}",
            )
            db.session.add_all([stuck, succeeded])
            db.session.commit()

            cancelled = cancel_existing_jobs_action(
                {"post_guid": post.guid, "current_job_id": "new-job-id"}
            )
            db.session.commit()

            assert cancelled == 1
            db.session.refresh(stuck)
            db.session.refresh(succeeded)
            assert stuck.status == "cancelled"
            assert stuck.error_message == "Superseded by a new processing job"
            # Terminal statuses are untouched.
            assert succeeded.status == "success"

    def test_upsert_resets_cancelled_row_back_to_pending(self, app):
        """After cancellation, the next run's upsert for the same chunk must
        reuse the cancelled row (clearing its error_message) instead of
        leaving the UI showing a stale `Superseded` message OR crashing on
        the unique-index collision.
        """
        with app.app_context():
            post = self._create_post("cancelled-then-reupsert-guid")
            existing = ModelCall(
                post_id=post.id,
                first_segment_sequence_num=2339,
                last_segment_sequence_num=2363,
                model_name="gemini/gemini-3-flash-preview",
                prompt="old prompt",
                status="cancelled",
                error_message="Superseded by a new processing job",
                response=None,
                retry_attempts=2,
            )
            db.session.add(existing)
            db.session.commit()

            result = upsert_model_call_action(
                {
                    "post_id": post.id,
                    "model_name": "gemini/gemini-3-flash-preview",
                    "first_segment_sequence_num": 2339,
                    "last_segment_sequence_num": 2363,
                    "prompt": "fresh prompt",
                }
            )
            db.session.commit()

            assert result == {"model_call_id": existing.id}
            db.session.refresh(existing)
            assert existing.status == "pending"
            assert existing.prompt == "fresh prompt"
            assert existing.retry_attempts == 0
            assert existing.error_message is None
