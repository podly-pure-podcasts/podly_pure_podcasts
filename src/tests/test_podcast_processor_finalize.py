from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models import Post, ProcessingJob
from podcast_processor.podcast_processor import PodcastProcessor


def _processor() -> PodcastProcessor:
    # Bypass __init__ to avoid beartype constructor checks on MagicMock doubles.
    processor = object.__new__(PodcastProcessor)
    processor.logger = MagicMock()
    processor.status_manager = MagicMock()
    processor._remove_unprocessed_audio = MagicMock()
    return processor


def _post() -> Post:
    return Post(id=7, guid="ep-7", unprocessed_audio_path="/in/ep.mp3", duration=3723)


def test_finalize_persists_processed_audio_duration() -> None:
    post = _post()
    with (
        patch(
            "podcast_processor.podcast_processor.get_audio_duration_ms",
            return_value=3_000_500,
        ) as probe,
        patch("podcast_processor.podcast_processor.writer_client") as writer,
    ):
        writer.update.return_value = SimpleNamespace(success=True)
        _processor()._finalize_processing(
            post, ProcessingJob(), "/out/ep.mp3", chapter_data="{}"
        )

    probe.assert_called_once_with("/out/ep.mp3")
    update_data = writer.update.call_args.args[2]
    assert update_data["duration"] == 3000.5
    assert post.duration == 3000.5


def test_finalize_keeps_stored_duration_when_probe_fails() -> None:
    post = _post()
    with (
        patch(
            "podcast_processor.podcast_processor.get_audio_duration_ms",
            return_value=None,
        ),
        patch("podcast_processor.podcast_processor.writer_client") as writer,
    ):
        writer.update.return_value = SimpleNamespace(success=True)
        _processor()._finalize_processing(post, ProcessingJob(), "/out/ep.mp3")

    assert "duration" not in writer.update.call_args.args[2]
    assert post.duration == 3723
