import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import ffmpeg
import pytest

from app.models import Post, ProcessingJob, TranscriptSegment
from podcast_processor.ad_classifier import ClassificationIncompleteError
from podcast_processor.audio import get_audio_duration_ms
from podcast_processor.podcast_processor import (
    PROCESSING_FAILED_CLIP_PATH,
    PodcastProcessor,
    ProcessorException,
)
from shared.test_utils import create_standard_test_config


def _make_processor() -> Any:
    # Bypass __init__ to avoid beartype constructor checks on MagicMock doubles.
    # Typed as Any because tests replace methods with MagicMock doubles.
    processor = object.__new__(PodcastProcessor)
    processor.config = create_standard_test_config()
    processor.logger = MagicMock()
    processor.status_manager = MagicMock()
    return processor


def _make_post(unprocessed_audio_path: str) -> Post:
    return Post(
        id=1,
        feed_id=1,
        guid="test-guid",
        title="Test Episode",
        download_url="https://example.com/test.mp3",
        unprocessed_audio_path=unprocessed_audio_path,
    )


def _make_silent_source(path: Path, seconds: float) -> None:
    (
        ffmpeg.input("anullsrc=r=22050:cl=mono", f="lavfi", t=seconds)
        .output(str(path), acodec="libmp3lame")
        .overwrite_output()
        .run(quiet=True)
    )


def _max_volume_db(path: Path, start: float, duration: float) -> float:
    _, stderr = (
        ffmpeg.input(str(path), ss=start, t=duration)
        .filter("volumedetect")
        .output("-", format="null")
        .run(capture_stderr=True)
    )
    match = re.search(r"max_volume: (-?[\d.]+) dB", stderr.decode())
    assert match is not None
    return float(match.group(1))


@pytest.fixture
def writer_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock()
    client.update.return_value = SimpleNamespace(success=True)
    monkeypatch.setattr("podcast_processor.podcast_processor.writer_client", client)
    return client


def test_incomplete_classification_publishes_without_ad_removal() -> None:
    """An unclassified chunk must not lead to cut audio and a finalized episode."""
    processor = _make_processor()
    processor.transcription_manager = MagicMock()
    processor.transcription_manager.transcribe.return_value = [
        TranscriptSegment(
            post_id=1, sequence_num=0, start_time=0.0, end_time=5.0, text="hello"
        )
    ]
    processor.audio_processor = MagicMock()
    # The real _classify_ad_segments runs; only the classifier itself is a double.
    processor.quote_anchor_classifier = MagicMock()
    processor.quote_anchor_classifier.classify.side_effect = (
        ClassificationIncompleteError("1 chunk(s) without a usable answer")
    )
    processor._finalize_processing = MagicMock()
    processor._publish_without_ad_removal = MagicMock()

    post = _make_post("/tmp/input.mp3")
    job = ProcessingJob(id="job-1", post_guid="test-guid", status="running")

    processor._perform_llm_based_processing(post, job, "/tmp/output.mp3")

    processor.quote_anchor_classifier.classify.assert_called_once()
    processor._publish_without_ad_removal.assert_called_once_with(
        post, job, "/tmp/output.mp3", None, "1 chunk(s) without a usable answer"
    )
    processor.audio_processor.process_audio.assert_not_called()
    processor._finalize_processing.assert_not_called()


def test_quote_anchor_incomplete_classification_publishes_without_ad_removal() -> None:
    processor = _make_processor()
    processor.transcription_manager = MagicMock()
    processor.transcription_manager.transcribe.return_value = [
        TranscriptSegment(
            post_id=1, sequence_num=0, start_time=0.0, end_time=5.0, text="hello"
        )
    ]
    processor.audio_processor = MagicMock()
    processor.quote_anchor_classifier = MagicMock()
    processor.quote_anchor_classifier.classify.side_effect = (
        ClassificationIncompleteError(
            "Ad classification incomplete for quote-anchor window: "
            "LLM response is not valid quote-ad JSON"
        )
    )
    processor._finalize_processing = MagicMock()
    processor._publish_without_ad_removal = MagicMock()

    post = _make_post("/tmp/input.mp3")
    job = ProcessingJob(id="job-1", post_guid="test-guid", status="running")

    processor._perform_llm_based_processing(post, job, "/tmp/output.mp3")

    processor.quote_anchor_classifier.classify.assert_called_once()
    processor._publish_without_ad_removal.assert_called_once()
    processor.audio_processor.process_audio.assert_not_called()
    processor._finalize_processing.assert_not_called()


def test_publish_without_ad_removal_prepends_notice(
    tmp_path: Path, writer_client: MagicMock
) -> None:
    source = tmp_path / "in.mp3"
    _make_silent_source(source, seconds=3.0)
    output = tmp_path / "out.mp3"
    processor = _make_processor()
    post = _make_post(str(source))
    job = ProcessingJob(id="job-1", post_guid="test-guid", status="running")

    processor._publish_without_ad_removal(
        post, job, str(output), None, "1 chunk(s) without a usable answer"
    )

    assert output.exists()
    assert not Path(f"{output}.partial").exists()
    assert not source.exists()

    clip_ms = get_audio_duration_ms(str(PROCESSING_FAILED_CLIP_PATH))
    output_ms = get_audio_duration_ms(str(output))
    assert clip_ms is not None and output_ms is not None
    assert abs(output_ms - (clip_ms + 3000)) < 300

    stream = ffmpeg.probe(str(output))["streams"][0]
    assert stream["codec_name"] == "mp3"
    assert int(stream["sample_rate"]) == 22050
    assert int(stream["channels"]) == 1

    # The spoken notice comes first, the silent source after it.
    assert _max_volume_db(output, 0.0, 3.0) > -40.0
    assert _max_volume_db(output, output_ms / 1000.0 - 2.0, 2.0) < -60.0

    # The marker is stored first, then the published file is recorded.
    marker_call, paths_call = writer_client.update.call_args_list
    assert marker_call.args == ("Post", 1, {"processing_failed": True})
    _, post_id, update_data = paths_call.args
    assert post_id == 1
    assert update_data["processed_audio_path"] == str(output)
    assert update_data["unprocessed_audio_path"] is None
    assert update_data["chapter_data"] is None

    final_call = processor.status_manager.update_job_status.call_args
    assert final_call.args[1] == "failed"
    assert "1 chunk(s) without a usable answer" in final_call.kwargs["error_message"]


def test_publish_without_ad_removal_publishes_nothing_when_marker_update_fails(
    tmp_path: Path, writer_client: MagicMock
) -> None:
    source = tmp_path / "in.mp3"
    _make_silent_source(source, seconds=1.0)
    output = tmp_path / "out.mp3"
    writer_client.update.return_value = SimpleNamespace(
        success=False, error="writer down"
    )
    processor = _make_processor()
    job = ProcessingJob(id="job-1", post_guid="test-guid", status="running")

    with pytest.raises(RuntimeError, match="writer down"):
        processor._publish_without_ad_removal(
            _make_post(str(source)), job, str(output), None, "incomplete"
        )

    assert not output.exists()
    assert not Path(f"{output}.partial").exists()
    assert source.exists()
    writer_client.update.assert_called_once()


def test_publish_without_ad_removal_keeps_marked_file_when_path_update_fails(
    tmp_path: Path, writer_client: MagicMock
) -> None:
    """With the marker stored, a later discovery of the file stays correct."""
    source = tmp_path / "in.mp3"
    _make_silent_source(source, seconds=1.0)
    output = tmp_path / "out.mp3"
    writer_client.update.side_effect = [
        SimpleNamespace(success=True),
        TimeoutError("writer reply lost"),
    ]
    processor = _make_processor()
    job = ProcessingJob(id="job-1", post_guid="test-guid", status="running")

    with pytest.raises(TimeoutError):
        processor._publish_without_ad_removal(
            _make_post(str(source)), job, str(output), None, "incomplete"
        )

    assert output.exists()
    assert source.exists()


def test_publish_without_ad_removal_stops_when_cancelled(
    tmp_path: Path, writer_client: MagicMock
) -> None:
    source = tmp_path / "in.mp3"
    _make_silent_source(source, seconds=1.0)
    output = tmp_path / "out.mp3"
    processor = _make_processor()
    job = ProcessingJob(id="job-1", post_guid="test-guid", status="running")

    with pytest.raises(ProcessorException, match="Cancelled"):
        processor._publish_without_ad_removal(
            _make_post(str(source)), job, str(output), lambda: True, "incomplete"
        )

    assert not output.exists()
    assert not Path(f"{output}.partial").exists()
    assert source.exists()
    writer_client.update.assert_not_called()
