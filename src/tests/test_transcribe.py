import logging
from typing import Any
from unittest.mock import MagicMock

import pytest
from openai.types.audio.transcription_segment import TranscriptionSegment

# from pytest_mock import MockerFixture


@pytest.mark.skip
def test_remote_transcribe() -> None:
    # import here instead of the toplevel because torch is not installed properly in CI.
    from podcast_processor.transcribe import (
        OpenAIWhisperTranscriber,
    )

    logger = logging.getLogger("global_logger")
    from shared.test_utils import create_standard_test_config

    config = create_standard_test_config().model_dump()

    transcriber = OpenAIWhisperTranscriber(logger, config)

    transcription = transcriber.transcribe("file.mp3")
    assert transcription == []


@pytest.mark.skip
def test_local_transcribe() -> None:
    # import here instead of the toplevel because torch is not installed properly in CI.
    from podcast_processor.transcribe import (
        LocalWhisperTranscriber,
    )

    logger = logging.getLogger("global_logger")
    transcriber = LocalWhisperTranscriber(logger, "base.en")
    transcription = transcriber.transcribe("src/tests/file.mp3")
    assert transcription == []


@pytest.mark.skip
def test_groq_transcribe(mocker: Any) -> None:
    # import here instead of the toplevel because dependencies aren't installed properly in CI.
    from podcast_processor.transcribe import (
        GroqWhisperTranscriber,
    )
    from shared.config import (
        GroqWhisperConfig,
    )

    # Mock the requests call
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "This is a test segment."},
            {"start": 1.0, "end": 2.0, "text": "This is another test segment."},
        ]
    }
    mocker.patch("requests.post", return_value=mock_response)

    # Mock file operations
    mocker.patch("builtins.open", mocker.mock_open(read_data="test audio data"))
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch("podcast_processor.audio.split_audio", return_value=[("test.mp3", 0)])
    mocker.patch("shutil.rmtree")

    logger = logging.getLogger("global_logger")
    config = GroqWhisperConfig(
        api_key="test_key", model="whisper-large-v3-turbo", language="en"
    )

    transcriber = GroqWhisperTranscriber(logger, config)
    transcription = transcriber.transcribe("test.mp3")

    assert len(transcription) == 2
    assert transcription[0].text == "This is a test segment."
    assert transcription[1].text == "This is another test segment."


def test_offset() -> None:
    # import here instead of the toplevel because torch is not installed properly in CI.
    from podcast_processor.transcribe import (
        OpenAIWhisperTranscriber,
    )

    assert OpenAIWhisperTranscriber.add_offset_to_segments(
        [
            TranscriptionSegment(
                id=1,
                avg_logprob=2,
                seek=6,
                temperature=7,
                text="hi",
                tokens=[],
                compression_ratio=3,
                no_speech_prob=4,
                start=12.345,
                end=45.678,
            )
        ],
        123,
    ) == [
        TranscriptionSegment(
            id=1,
            avg_logprob=2,
            seek=6,
            temperature=7,
            text="hi",
            tokens=[],
            compression_ratio=3,
            no_speech_prob=4,
            start=12.468,
            end=45.800999999999995,
        )
    ]


def test_local_transcriber_uses_gpu_when_available(
    mocker: Any,
) -> None:
    """LocalWhisperTranscriber should pass device=cuda when torch.cuda.is_available()."""
    from podcast_processor.transcribe import (
        LocalWhisperTranscriber,
    )

    logger = logging.getLogger("global_logger")
    transcriber = LocalWhisperTranscriber(logger, "base.en")

    # Mock torch to report CUDA available
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = True

    # Mock whisper.load_model and model.transcribe
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"segments": []}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_whisper.available_models.return_value = ["base.en"]

    # Patch in sys.modules so the in-method "import torch"/"import whisper" resolve
    mocker.patch.dict("sys.modules", {"torch": mock_torch, "whisper": mock_whisper})
    # Also patch on the module object itself (create=True for in-method imports)
    mocker.patch("podcast_processor.transcribe.torch", mock_torch, create=True)
    mocker.patch("podcast_processor.transcribe.whisper", mock_whisper, create=True)

    transcriber.transcribe("dummy.mp3")

    # Verify load_model was called with device="cuda"
    mock_whisper.load_model.assert_called_once_with(name="base.en", device="cuda")
    # Verify transcribe was called with fp16=True (GPU path)
    mock_model.transcribe.assert_called_once()
    call_kwargs = mock_model.transcribe.call_args[1]
    assert call_kwargs["fp16"] is True


def test_local_transcriber_uses_cpu_when_no_gpu(
    mocker: Any,
) -> None:
    """LocalWhisperTranscriber should fall back to cpu when CUDA is not available."""
    from podcast_processor.transcribe import (
        LocalWhisperTranscriber,
    )

    logger = logging.getLogger("global_logger")
    transcriber = LocalWhisperTranscriber(logger, "base.en")

    # Mock torch to report no CUDA
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    # Mock whisper
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"segments": []}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    mock_whisper.available_models.return_value = ["base.en"]

    mocker.patch.dict("sys.modules", {"torch": mock_torch, "whisper": mock_whisper})
    mocker.patch("podcast_processor.transcribe.torch", mock_torch, create=True)
    mocker.patch("podcast_processor.transcribe.whisper", mock_whisper, create=True)

    transcriber.transcribe("dummy.mp3")

    # Verify load_model was called with device="cpu"
    mock_whisper.load_model.assert_called_once_with(name="base.en", device="cpu")
    # Verify transcribe was called with fp16=False (CPU path)
    call_kwargs = mock_model.transcribe.call_args[1]
    assert call_kwargs["fp16"] is False
