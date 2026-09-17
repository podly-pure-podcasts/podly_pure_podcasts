import logging
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from app.extensions import db
from app.models import Feed, ModelCall, Post, TranscriptSegment
from podcast_processor.transcribe import Segment, Transcriber
from podcast_processor.transcription_manager import TranscriptionManager
from shared.config import Config, TestWhisperConfig
from shared.test_utils import create_standard_test_config


class MockTranscriber(Transcriber):
    """Mock transcriber for testing TranscriptionManager."""

    def __init__(self, mock_response: list[Segment] | Exception | None = None):
        self.mock_response: list[Segment] | Exception = mock_response or []
        self._model_name = "mock_transcriber"

    @property
    def model_name(self) -> str:
        """Implementation of the abstract property"""
        return self._model_name

    def transcribe(self, audio_file_path: str, language: str) -> list[Segment]:
        """Return mock segments or raise exception based on configuration."""
        del audio_file_path, language
        if isinstance(self.mock_response, Exception):
            raise self.mock_response
        return self.mock_response


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    """Create and configure a Flask app for testing."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    with app.app_context():
        db.init_app(app)
        db.create_all()
        yield app


@pytest.fixture
def test_config() -> Config:
    config = create_standard_test_config()
    # Override whisper config to use test mode
    config.whisper = TestWhisperConfig()
    return config


@pytest.fixture
def test_logger() -> logging.Logger:
    return logging.getLogger("test_logger")


@pytest.fixture
def mock_db_session() -> MagicMock:
    """Create a mock database session"""
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()
    mock_session.commit = MagicMock()
    mock_session.rollback = MagicMock()
    return mock_session


@pytest.fixture
def mock_transcriber() -> MockTranscriber:
    """Return a mock transcriber for testing."""
    return MockTranscriber(
        [
            Segment(start=0.0, end=5.0, text="Test segment 1"),
            Segment(start=5.0, end=10.0, text="Test segment 2"),
        ]
    )


@pytest.fixture
def test_manager(
    test_config: Config,
    test_logger: logging.Logger,
    mock_db_session: MagicMock,
    mock_transcriber: MockTranscriber,
    app: Flask,
) -> TranscriptionManager:
    """Return a TranscriptionManager instance for testing."""
    with app.app_context():
        # We need to create mock query objects with proper structure
        mock_model_call_query = MagicMock()
        mock_segment_query = MagicMock()

        # Create a manager with our mocks
        return TranscriptionManager(
            test_logger,
            test_config,
            model_call_query=mock_model_call_query,
            segment_query=mock_segment_query,
            db_session=mock_db_session,
            transcriber=mock_transcriber,
        )


def test_check_existing_transcription_success(
    test_manager: TranscriptionManager,
    app: Flask,
) -> None:
    """Test finding existing successful transcription"""
    post = Post(id=1, title="Test Post")

    # Create test data
    model_call = ModelCall(
        post_id=1,
        model_name=test_manager.transcriber.model_name,
        status="success",
        first_segment_sequence_num=0,
        last_segment_sequence_num=1,
    )
    segments = [
        TranscriptSegment(
            post_id=1, sequence_num=0, start_time=0.0, end_time=5.0, text="Segment 1"
        ),
        TranscriptSegment(
            post_id=1, sequence_num=1, start_time=5.0, end_time=10.0, text="Segment 2"
        ),
    ]

    with app.app_context():
        # Configure the existing mocks in the manager
        test_manager.model_call_query.filter_by().one_or_none.return_value = model_call
        test_manager.segment_query.filter_by().order_by().all.return_value = segments

        result = test_manager._check_existing_transcription(post, "en")

        assert result is not None
        assert len(result) == 2
        assert result[0].text == "Segment 1"
        assert result[1].text == "Segment 2"


def test_check_existing_transcription_no_model_call(
    test_manager: TranscriptionManager,
    app: Flask,
) -> None:
    """Test when no existing ModelCall exists"""
    post = Post(id=1, title="Test Post")

    with app.app_context():
        # Set return value for the existing mock in the manager
        test_manager.model_call_query.filter_by().one_or_none.return_value = None

        result = test_manager._check_existing_transcription(post, "en")
        assert result is None


def test_transcribe_new(
    test_config: Config,
    test_logger: logging.Logger,
    app: Flask,
) -> None:
    """Test transcribing a new audio file"""
    with app.app_context():
        feed = Feed(title="Test Feed", rss_url="http://example.com/rss.xml")
        post = Post(
            feed=feed,
            guid="guid-1",
            download_url="http://example.com/audio-1.mp3",
            title="Test Post",
            unprocessed_audio_path="/path/to/audio.mp3",
        )
        db.session.add_all([feed, post])
        db.session.commit()

        transcriber = MockTranscriber(
            [
                Segment(start=0.0, end=5.0, text="Test segment 1"),
                Segment(start=5.0, end=10.0, text="Test segment 2"),
            ]
        )
        manager = TranscriptionManager(
            test_logger,
            test_config,
            db_session=db.session,
            transcriber=transcriber,
        )

        segments = manager.transcribe(post)

        assert len(segments) == 2
        assert segments[0].text == "Test segment 1"
        assert segments[1].text == "Test segment 2"
        assert TranscriptSegment.query.filter_by(post_id=post.id).count() == 2
        assert ModelCall.query.filter_by(post_id=post.id).count() == 1
        assert ModelCall.query.filter_by(post_id=post.id).first().status == "success"


def test_transcribe_handles_error(
    test_config: Config,
    test_logger: logging.Logger,
    app: Flask,
) -> None:
    """Test error handling during transcription"""
    with app.app_context():
        feed = Feed(title="Test Feed", rss_url="http://example.com/rss.xml")
        post = Post(
            feed=feed,
            guid="guid-err",
            download_url="http://example.com/audio-err.mp3",
            title="Test Post",
            unprocessed_audio_path="/path/to/audio.mp3",
        )
        db.session.add_all([feed, post])
        db.session.commit()

        # Create a mock transcriber that raises an exception
        error_transcriber = MockTranscriber(Exception("Transcription failed"))

        manager = TranscriptionManager(
            test_logger,
            test_config,
            db_session=db.session,
            transcriber=error_transcriber,
        )

        # Test the exception
        with pytest.raises(Exception) as exc_info:
            manager.transcribe(post)

        assert str(exc_info.value) == "Transcription failed"
        call = (
            ModelCall.query.filter_by(post_id=post.id)
            .order_by(ModelCall.timestamp.desc())
            .first()
        )
        assert call is not None
        assert call.status == "failed_permanent"
        assert call.error_message == "Transcription failed"


def test_transcribe_reuses_placeholder_model_call(
    test_config: Config,
    test_logger: logging.Logger,
    app: Flask,
) -> None:
    """Ensure we reuse existing placeholder ModelCall rows instead of crashing on uniqueness."""
    with app.app_context():
        feed = Feed(title="Test Feed", rss_url="http://example.com/rss.xml")
        post = Post(
            feed=feed,
            guid="guid-123",
            download_url="http://example.com/audio.mp3",
            title="Test Post",
            unprocessed_audio_path="/tmp/audio.mp3",
        )
        db.session.add_all([feed, post])
        db.session.commit()

        existing_call = ModelCall(
            post_id=post.id,
            model_name="mock_transcriber",
            first_segment_sequence_num=0,
            last_segment_sequence_num=-1,
            prompt="Whisper transcription job",
            status="failed_permanent",
            language="en",
        )
        db.session.add(existing_call)
        db.session.commit()

        manager = TranscriptionManager(
            test_logger,
            test_config,
            db_session=db.session,
            transcriber=MockTranscriber(
                [
                    Segment(start=0.0, end=5.0, text="Segment 1"),
                    Segment(start=5.0, end=10.0, text="Segment 2"),
                ]
            ),
        )

        segments = manager.transcribe(post)

        assert len(segments) == 2
        assert ModelCall.query.count() == 1
        refreshed_call = ModelCall.query.first()
        assert refreshed_call.id == existing_call.id
        assert refreshed_call.status == "success"
        assert refreshed_call.last_segment_sequence_num == 1


def test_transcribe_passes_language_to_transcriber(
    test_config: Config,
    test_logger: logging.Logger,
    mock_db_session: MagicMock,
    app: Flask,
) -> None:
    """Language is forwarded to the underlying transcriber."""
    post = Post(id=99, title="Test Post", unprocessed_audio_path="/path/to/audio.mp3")

    dummy_call = ModelCall(
        id=1,
        post_id=99,
        model_name="mock_transcriber",
        status="placeholder",
        first_segment_sequence_num=0,
        last_segment_sequence_num=-1,
    )

    mock_model_call_query = MagicMock()
    mock_model_call_query.filter_by().one_or_none.return_value = None
    mock_db_session.execute.return_value = MagicMock(lastrowid=1)
    mock_db_session.get.return_value = dummy_call

    mock_segment_query = MagicMock()
    mock_segment_query.filter_by().order_by().all.return_value = []

    segments_out = [Segment(start=0.0, end=1.0, text="Hallo")]
    transcriber = MockTranscriber(segments_out)

    with app.app_context():
        manager = TranscriptionManager(
            test_logger,
            test_config,
            model_call_query=mock_model_call_query,
            segment_query=mock_segment_query,
            db_session=mock_db_session,
            transcriber=transcriber,
        )

        with patch.object(
            transcriber, "transcribe", wraps=transcriber.transcribe
        ) as mock_transcribe:
            manager.transcribe(post, language="de")
            mock_transcribe.assert_called_once_with(
                post.unprocessed_audio_path, language="de"
            )


def test_language_change_invalidates_cache(
    test_config: Config,
    test_logger: logging.Logger,
    app: Flask,
) -> None:
    """Changing the per-feed language forces a fresh transcription instead of returning
    the cached transcript from the prior language."""
    with app.app_context():
        feed = Feed(title="Test Feed", rss_url="http://example.com/rss.xml")
        post = Post(
            feed=feed,
            guid="guid-lang",
            download_url="http://example.com/audio.mp3",
            title="Test Post",
            unprocessed_audio_path="/path/to/audio.mp3",
        )
        db.session.add_all([feed, post])
        db.session.commit()

        en_transcript = [Segment(start=0.0, end=1.0, text="English")]
        en_manager = TranscriptionManager(
            test_logger,
            test_config,
            db_session=db.session,
            transcriber=MockTranscriber(en_transcript),
        )
        en_result = en_manager.transcribe(post, language="en")
        assert [s.text for s in en_result] == ["English"]
        assert ModelCall.query.filter_by(post_id=post.id).count() == 1

        de_transcript = [Segment(start=0.0, end=1.0, text="Deutsch")]
        de_manager = TranscriptionManager(
            test_logger,
            test_config,
            db_session=db.session,
            transcriber=MockTranscriber(de_transcript),
        )
        de_result = de_manager.transcribe(post, language="de")
        assert [s.text for s in de_result] == ["Deutsch"]
        # Two ModelCall rows — one per language — so the en cache wasn't returned.
        en_call = ModelCall.query.filter_by(post_id=post.id, language="en").one()
        de_call = ModelCall.query.filter_by(post_id=post.id, language="de").one()
        # The de transcription overwrote the shared segments table, so the en
        # row must be marked superseded — otherwise a later en lookup would
        # return de segments labeled as English.
        assert en_call.status == "superseded"
        assert de_call.status == "success"

        # Re-running with the original language must re-transcribe (cache miss
        # because the en row is superseded) — returns English from the mock.
        en_again = en_manager.transcribe(post, language="en")
        assert [s.text for s in en_again] == ["English"]
