import logging
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path
<<<<<<< HEAD
from typing import Any
=======
from typing import Any, List
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

from groq import Groq
from openai import OpenAI
from openai.types.audio.transcription_segment import TranscriptionSegment
from pydantic import BaseModel

from podcast_processor.audio import split_audio
from shared.config import GroqWhisperConfig, RemoteWhisperConfig


class Segment(BaseModel):
    start: float
    end: float
    text: str


class Transcriber(ABC):
<<<<<<< HEAD
=======

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
<<<<<<< HEAD
    def transcribe(self, audio_file_path: str) -> list[Segment]:
=======
    def transcribe(self, audio_file_path: str) -> List[Segment]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        pass


class LocalTranscriptSegment(BaseModel):
    id: int
    seek: int
    start: float
    end: float
    text: str
<<<<<<< HEAD
    tokens: list[int]
=======
    tokens: List[int]
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    temperature: float
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float

    def to_segment(self) -> Segment:
        return Segment(start=self.start, end=self.end, text=self.text)


class TestWhisperTranscriber(Transcriber):
<<<<<<< HEAD
=======

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    @property
    def model_name(self) -> str:
        return "test_whisper"

<<<<<<< HEAD
    def transcribe(self, audio_file_path: str) -> list[Segment]:
        del audio_file_path
=======
    def transcribe(self, _: str) -> List[Segment]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        self.logger.info("Using test whisper")
        return [
            Segment(start=0, end=1, text="This is a test"),
            Segment(start=1, end=2, text="This is another test"),
        ]


class LocalWhisperTranscriber(Transcriber):
<<<<<<< HEAD
=======

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    def __init__(self, logger: logging.Logger, whisper_model: str):
        self.logger = logger
        self.whisper_model = whisper_model

    @property
    def model_name(self) -> str:
        return f"local_{self.whisper_model}"

    @staticmethod
    def convert_to_pydantic(
<<<<<<< HEAD
        transcript_data: list[Any],
    ) -> list[LocalTranscriptSegment]:
        return [LocalTranscriptSegment(**item) for item in transcript_data]

    @staticmethod
    def local_seg_to_seg(local_segments: list[LocalTranscriptSegment]) -> list[Segment]:
        return [seg.to_segment() for seg in local_segments]

    def transcribe(self, audio_file_path: str) -> list[Segment]:
        # Import whisper only when needed to avoid CUDA dependencies during module import
        try:
            import whisper
=======
        transcript_data: List[Any],
    ) -> List[LocalTranscriptSegment]:
        return [LocalTranscriptSegment(**item) for item in transcript_data]

    @staticmethod
    def local_seg_to_seg(local_segments: List[LocalTranscriptSegment]) -> List[Segment]:
        return [seg.to_segment() for seg in local_segments]

    def transcribe(self, audio_file_path: str) -> List[Segment]:
        # Import whisper only when needed to avoid CUDA dependencies during module import
        try:
            import whisper  # type: ignore[import-untyped]
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        except ImportError as e:
            self.logger.error(f"Failed to import whisper: {e}")
            raise ImportError(
                "whisper library is required for LocalWhisperTranscriber"
            ) from e

        self.logger.info("Using local whisper")
        models = whisper.available_models()
        self.logger.info(f"Available models: {models}")

        model = whisper.load_model(name=self.whisper_model)

        self.logger.info("Beginning transcription")
        start = time.time()
        result = model.transcribe(audio_file_path, fp16=False, language="English")
        end = time.time()
        elapsed = end - start
        self.logger.info(f"Transcription completed in {elapsed}")
        segments = result["segments"]
        typed_segments = self.convert_to_pydantic(segments)

        return self.local_seg_to_seg(typed_segments)


class OpenAIWhisperTranscriber(Transcriber):
<<<<<<< HEAD
=======

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    def __init__(self, logger: logging.Logger, config: RemoteWhisperConfig):
        self.logger = logger
        self.config = config

        self.openai_client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_sec,
        )

    @property
    def model_name(self) -> str:
        return self.config.model  # e.g. "whisper-1"

<<<<<<< HEAD
    def transcribe(self, audio_file_path: str) -> list[Segment]:
        self.logger.info(
            "[WHISPER_REMOTE] Starting remote whisper transcription for: %s",
            audio_file_path,
        )
=======
    def transcribe(self, audio_file_path: str) -> List[Segment]:
        self.logger.info("Using remote whisper")
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        audio_chunk_path = audio_file_path + "_parts"

        chunks = split_audio(
            Path(audio_file_path),
            Path(audio_chunk_path),
            self.config.chunksize_mb * 1024 * 1024,
        )

<<<<<<< HEAD
        self.logger.info("[WHISPER_REMOTE] Processing %d chunks", len(chunks))
        all_segments: list[TranscriptionSegment] = []

        for idx, chunk in enumerate(chunks):
            chunk_path, offset = chunk
            self.logger.info(
                "[WHISPER_REMOTE] Processing chunk %d/%d: %s",
                idx + 1,
                len(chunks),
                chunk_path,
            )
            segments = self.get_segments_for_chunk(str(chunk_path))
            self.logger.info(
                "[WHISPER_REMOTE] Chunk %d/%d complete: %d segments",
                idx + 1,
                len(chunks),
                len(segments),
            )
            all_segments.extend(self.add_offset_to_segments(segments, offset))

        shutil.rmtree(audio_chunk_path)
        self.logger.info(
            "[WHISPER_REMOTE] Transcription complete: %d total segments",
            len(all_segments),
        )
        return self.convert_segments(all_segments)

    @staticmethod
    def convert_segments(segments: list[TranscriptionSegment]) -> list[Segment]:
=======
        all_segments: List[TranscriptionSegment] = []

        for chunk in chunks:
            chunk_path, offset = chunk
            segments = self.get_segments_for_chunk(str(chunk_path))
            all_segments.extend(self.add_offset_to_segments(segments, offset))

        shutil.rmtree(audio_chunk_path)
        return self.convert_segments(all_segments)

    @staticmethod
    def convert_segments(segments: List[TranscriptionSegment]) -> List[Segment]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        return [
            Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
            )
            for seg in segments
        ]

    @staticmethod
    def add_offset_to_segments(
<<<<<<< HEAD
        segments: list[TranscriptionSegment], offset_ms: int
    ) -> list[TranscriptionSegment]:
=======
        segments: List[TranscriptionSegment], offset_ms: int
    ) -> List[TranscriptionSegment]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        offset_sec = float(offset_ms) / 1000.0
        for segment in segments:
            segment.start += offset_sec
            segment.end += offset_sec

        return segments

<<<<<<< HEAD
    def get_segments_for_chunk(self, chunk_path: str) -> list[TranscriptionSegment]:
        with open(chunk_path, "rb") as f:
            self.logger.info(
                "[WHISPER_API_CALL] Sending chunk to API: %s (timeout=%ds)",
                chunk_path,
                self.config.timeout_sec,
            )
=======
    def get_segments_for_chunk(self, chunk_path: str) -> List[TranscriptionSegment]:
        with open(chunk_path, "rb") as f:
            self.logger.info(f"Transcribing chunk {chunk_path}")
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

            transcription = self.openai_client.audio.transcriptions.create(
                model=self.config.model,
                file=f,
                timestamp_granularities=["segment"],
                language=self.config.language,
                response_format="verbose_json",
            )

            self.logger.debug("Got transcription")

            segments = transcription.segments
            assert segments is not None

            self.logger.debug(f"Got {len(segments)} segments")

            return segments


class GroqTranscriptionSegment(BaseModel):
    start: float
    end: float
    text: str


class GroqWhisperTranscriber(Transcriber):
<<<<<<< HEAD
=======

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    def __init__(self, logger: logging.Logger, config: GroqWhisperConfig):
        self.logger = logger
        self.config = config
        self.client = Groq(
            api_key=config.api_key,
            max_retries=config.max_retries,
        )

    @property
    def model_name(self) -> str:
        return f"groq_{self.config.model}"

<<<<<<< HEAD
    def transcribe(self, audio_file_path: str) -> list[Segment]:
        self.logger.info(
            "[WHISPER_GROQ] Starting Groq whisper transcription for: %s",
            audio_file_path,
        )
        audio_chunk_path = audio_file_path + "_parts"

        # 12MB seems to cause instability in Groq
        chunks = split_audio(
            Path(audio_file_path), Path(audio_chunk_path), 6 * 1024 * 1024
        )

        self.logger.info("[WHISPER_GROQ] Processing %d chunks", len(chunks))
        all_segments: list[GroqTranscriptionSegment] = []

        for idx, chunk in enumerate(chunks):
            chunk_path, offset = chunk
            self.logger.info(
                "[WHISPER_GROQ] Processing chunk %d/%d: %s",
                idx + 1,
                len(chunks),
                chunk_path,
            )
            segments = self.get_segments_for_chunk(str(chunk_path))
            self.logger.info(
                "[WHISPER_GROQ] Chunk %d/%d complete: %d segments",
                idx + 1,
                len(chunks),
                len(segments),
            )
            all_segments.extend(self.add_offset_to_segments(segments, offset))

        shutil.rmtree(audio_chunk_path)
        self.logger.info(
            "[WHISPER_GROQ] Transcription complete: %d total segments",
            len(all_segments),
        )
        return self.convert_segments(all_segments)

    @staticmethod
    def convert_segments(segments: list[GroqTranscriptionSegment]) -> list[Segment]:
=======
    def transcribe(self, audio_file_path: str) -> List[Segment]:
        self.logger.info("Using Groq whisper")
        audio_chunk_path = audio_file_path + "_parts"

        chunks = split_audio(
            Path(audio_file_path), Path(audio_chunk_path), 12 * 1024 * 1024
        )

        all_segments: List[GroqTranscriptionSegment] = []

        for chunk in chunks:
            chunk_path, offset = chunk
            segments = self.get_segments_for_chunk(str(chunk_path))
            all_segments.extend(self.add_offset_to_segments(segments, offset))

        shutil.rmtree(audio_chunk_path)
        return self.convert_segments(all_segments)

    @staticmethod
    def convert_segments(segments: List[GroqTranscriptionSegment]) -> List[Segment]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        return [
            Segment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
            )
            for seg in segments
        ]

    @staticmethod
    def add_offset_to_segments(
<<<<<<< HEAD
        segments: list[GroqTranscriptionSegment], offset_ms: int
    ) -> list[GroqTranscriptionSegment]:
=======
        segments: List[GroqTranscriptionSegment], offset_ms: int
    ) -> List[GroqTranscriptionSegment]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        offset_sec = float(offset_ms) / 1000.0
        for segment in segments:
            segment.start += offset_sec
            segment.end += offset_sec

        return segments

<<<<<<< HEAD
    def get_segments_for_chunk(self, chunk_path: str) -> list[GroqTranscriptionSegment]:
        retries = self.config.max_retries if self.config.max_retries is not None else 0
        max_attempts = retries + 1
        for attempt in range(1, max_attempts + 1):
            self.logger.info(
                "[GROQ_API_CALL] Sending chunk to Groq API: %s (attempt %d/%d)",
                chunk_path,
                attempt,
                max_attempts,
            )
            try:
                transcription = self.client.audio.transcriptions.create(
                    file=Path(chunk_path),
                    model=self.config.model,
                    response_format="verbose_json",  # Ensure segments are included
                    language=self.config.language,
                )
            except Exception as exc:
                self.logger.warning(
                    "[GROQ_API_CALL] Attempt %d/%d failed for %s: %s",
                    attempt,
                    max_attempts,
                    chunk_path,
                    exc,
                )
                if attempt == max_attempts:
                    raise
                time.sleep(1.5**attempt)
                continue

            self.logger.info(
                "[GROQ_API_CALL] Received response from Groq API for: %s (attempt %d/%d)",
                chunk_path,
                attempt,
                max_attempts,
            )

            if transcription.segments is None:  # type: ignore [attr-defined]
                self.logger.warning(
                    "[GROQ_API_CALL] No segments found in transcription for %s",
                    chunk_path,
                )
                return []

            groq_segments = [
                GroqTranscriptionSegment(
                    start=seg["start"], end=seg["end"], text=seg["text"]
                )
                for seg in transcription.segments  # type: ignore [attr-defined]
            ]

            self.logger.info(
                "[GROQ_API_CALL] Got %d segments from chunk (attempt %d/%d)",
                len(groq_segments),
                attempt,
                max_attempts,
            )
            return groq_segments

        # unreachable, but satisfies type checker
        return []
=======
    def get_segments_for_chunk(self, chunk_path: str) -> List[GroqTranscriptionSegment]:

        self.logger.info(f"Transcribing chunk {chunk_path} using groq client")
        transcription = self.client.audio.transcriptions.create(
            file=Path(chunk_path),
            model=self.config.model,
            response_format="verbose_json",  # Ensure segments are included
            language=self.config.language,
        )
        self.logger.debug("Got transcription from groq client")

        if transcription.segments is None:  # type: ignore [attr-defined]
            self.logger.warning(f"No segments found in transcription for {chunk_path}")
            return []

        groq_segments = [
            GroqTranscriptionSegment(
                start=seg["start"], end=seg["end"], text=seg["text"]
            )
            for seg in transcription.segments  # type: ignore [attr-defined]
        ]

        self.logger.debug(f"Got {len(groq_segments)} segments")
        return groq_segments
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
