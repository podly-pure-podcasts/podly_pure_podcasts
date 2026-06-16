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


def test_google_gemini_audio_transcriber_parses_segments(mocker: Any) -> None:
    from podcast_processor.transcribe import GoogleGeminiAudioTranscriber
    from shared.config import GoogleWhisperConfig

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": (
                                '{"segments":[{"start":0.5,"end":2.0,'
                                '"text":"Svensk testtext."}]}'
                            )
                        }
                    ]
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    post_mock = mocker.patch(
        "podcast_processor.transcribe.requests.post", return_value=mock_response
    )
    mocker.patch("builtins.open", mocker.mock_open(read_data=b"test audio data"))

    transcriber = GoogleGeminiAudioTranscriber(
        logging.getLogger("test"),
        GoogleWhisperConfig(api_key="gemini-key"),
    )

    segments = transcriber.get_segments_for_chunk("clip.mp3")

    assert segments[0].text == "Svensk testtext."
    assert segments[0].start == 0.5
    post_mock.assert_called_once()
    _, kwargs = post_mock.call_args
    assert kwargs["params"]["key"] == "gemini-key"
    assert kwargs["json"]["contents"][0]["parts"][1]["inline_data"]["mime_type"] == (
        "audio/mpeg"
    )


def test_google_gemini_audio_transcriber_offsets_segments() -> None:
    from podcast_processor.transcribe import (
        GeminiTranscriptionSegment,
        GoogleGeminiAudioTranscriber,
    )

    segments = [
        GeminiTranscriptionSegment(start=1.0, end=3.0, text="hej"),
    ]

    shifted = GoogleGeminiAudioTranscriber.add_offset_to_segments(segments, 2500)

    assert shifted[0].start == 3.5
    assert shifted[0].end == 5.5
