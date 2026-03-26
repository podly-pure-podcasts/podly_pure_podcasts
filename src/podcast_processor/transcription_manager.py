import logging
<<<<<<< HEAD
from typing import Any

from app.extensions import db
from app.models import ModelCall, Post, TranscriptSegment
from app.writer.client import writer_client
=======
from typing import Any, List, Optional

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Identification, ModelCall, Post, TranscriptSegment
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
from shared.config import (
    Config,
    GroqWhisperConfig,
    LocalWhisperConfig,
    RemoteWhisperConfig,
    TestWhisperConfig,
)

from .transcribe import (
    GroqWhisperTranscriber,
    LocalWhisperTranscriber,
    OpenAIWhisperTranscriber,
    TestWhisperTranscriber,
    Transcriber,
)


class TranscriptionManager:
    """Handles the transcription of podcast audio files."""

    def __init__(
        self,
        logger: logging.Logger,
        config: Config,
<<<<<<< HEAD
        model_call_query: Any | None = None,
        segment_query: Any | None = None,
        db_session: Any | None = None,
        transcriber: Transcriber | None = None,
=======
        model_call_query: Optional[Any] = None,
        segment_query: Optional[Any] = None,
        db_session: Optional[Any] = None,
        transcriber: Optional[Transcriber] = None,
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    ):
        self.logger = logger
        self.config = config
        self.transcriber = transcriber or self._create_transcriber()
<<<<<<< HEAD
        self._model_call_query_provided = model_call_query is not None
        self.model_call_query = model_call_query or ModelCall.query
        self._segment_query_provided = segment_query is not None
=======
        self.model_call_query = model_call_query or ModelCall.query
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        self.segment_query = segment_query or TranscriptSegment.query
        self.db_session = db_session or db.session

    def _create_transcriber(self) -> Transcriber:
        """Create the appropriate transcriber based on configuration."""
        assert self.config.whisper is not None, (
            "validate_whisper_config ensures that even if old style whisper "
            "config is given, it will be translated and config.whisper set."
        )

        if isinstance(self.config.whisper, TestWhisperConfig):
            return TestWhisperTranscriber(self.logger)
        if isinstance(self.config.whisper, RemoteWhisperConfig):
            return OpenAIWhisperTranscriber(self.logger, self.config.whisper)
        if isinstance(self.config.whisper, LocalWhisperConfig):
            return LocalWhisperTranscriber(self.logger, self.config.whisper.model)
        if isinstance(self.config.whisper, GroqWhisperConfig):
            return GroqWhisperTranscriber(self.logger, self.config.whisper)
        raise ValueError(f"unhandled whisper config {self.config.whisper}")

    def _check_existing_transcription(
        self, post: Post
<<<<<<< HEAD
    ) -> list[TranscriptSegment] | None:
        """Checks for existing successful transcription and returns segments if valid.

        NOTE: Defaults to using self.db_session for queries to keep a single session,
        but will honor injected model_call_query/segment_query when provided (e.g. tests).
        """
        model_call_query = (
            self.model_call_query
            if self._model_call_query_provided
            else self.db_session.query(ModelCall)
        )
        segment_query = (
            self.segment_query
            if self._segment_query_provided
            else self.db_session.query(TranscriptSegment)
        )

        existing_whisper_call = (
            model_call_query.filter_by(
=======
    ) -> Optional[List[TranscriptSegment]]:
        """Checks for existing successful transcription and returns segments if valid."""
        existing_whisper_call = (
            self.model_call_query.filter_by(
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
                post_id=post.id,
                model_name=self.transcriber.model_name,
                status="success",
            )
            .order_by(ModelCall.timestamp.desc())
            .first()
        )

        if existing_whisper_call:
            self.logger.info(
                f"Found existing successful Whisper ModelCall {existing_whisper_call.id} for post {post.id}."
            )
<<<<<<< HEAD
            db_segments: list[TranscriptSegment] = (
                segment_query.filter_by(post_id=post.id)
=======
            db_segments: List[TranscriptSegment] = (
                self.segment_query.filter_by(post_id=post.id)
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
                .order_by(TranscriptSegment.sequence_num)
                .all()
            )
            if db_segments:
                if (
                    existing_whisper_call.last_segment_sequence_num
                    == len(db_segments) - 1
                ):
                    self.logger.info(
                        f"Returning {len(db_segments)} existing transcript segments from database for post {post.id}."
                    )
                    return db_segments
                self.logger.warning(
                    f"ModelCall {existing_whisper_call.id} for post {post.id} indicates {existing_whisper_call.last_segment_sequence_num + 1} segments, but found {len(db_segments)} in DB. Re-transcribing."
                )
            else:
                self.logger.warning(
                    f"Successful ModelCall {existing_whisper_call.id} found for post {post.id}, but no transcript segments in DB. Re-transcribing."
                )
        else:
            self.logger.info(
                f"No existing successful Whisper ModelCall found for post {post.id} with model {self.transcriber.model_name}. Proceeding to transcribe."
            )
        return None

<<<<<<< HEAD
    def get_reusable_transcription(self, post: Post) -> list[TranscriptSegment] | None:
        """Return existing transcript segments only when they are reusable as-is.

        Reuse requires a successful Whisper model call for the active transcriber
        model and a matching set of persisted transcript segments.
        """
        return self._check_existing_transcription(post)

    def _get_or_create_whisper_model_call(self, post: Post) -> ModelCall:
        """Create or reuse the placeholder ModelCall row for a Whisper run via writer."""
        result = writer_client.action(
            "upsert_whisper_model_call",
            {
                "post_id": post.id,
                "model_name": self.transcriber.model_name,
                "first_segment_sequence_num": 0,
                "last_segment_sequence_num": -1,
                "prompt": "Whisper transcription job",
            },
            wait=True,
        )
        if not result or not result.success:
            raise RuntimeError(getattr(result, "error", "Failed to upsert ModelCall"))

        model_call_id = (result.data or {}).get("model_call_id")
        if model_call_id is None:
            raise RuntimeError("Writer did not return model_call_id")
        model_call = self.db_session.get(ModelCall, int(model_call_id))
        if model_call is None:
            raise RuntimeError(f"ModelCall {model_call_id} not found after upsert")
        return model_call

    def transcribe(self, post: Post) -> list[TranscriptSegment]:
=======
    def transcribe(self, post: Post) -> List[TranscriptSegment]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        """
        Transcribes a podcast audio file, or retrieves existing transcription.

        Args:
            post: The Post object containing the podcast audio to transcribe

        Returns:
            A list of TranscriptSegment objects with the transcription results
        """
        self.logger.info(
            f"Starting transcription process for post {post.id} using {self.transcriber.model_name}"
        )

<<<<<<< HEAD
        existing_segments = self.get_reusable_transcription(post)
        if existing_segments is not None:
            return existing_segments

        # Create or reuse the ModelCall record for this transcription attempt
        current_whisper_call = self._get_or_create_whisper_model_call(post)
        self.logger.info(
            f"Prepared Whisper ModelCall {current_whisper_call.id} for post {post.id}."
=======
        existing_segments = self._check_existing_transcription(post)
        if existing_segments is not None:
            return existing_segments

        # Create a new ModelCall record for this transcription attempt (upsert-safe)
        current_whisper_call = ModelCall(
            post_id=post.id,
            model_name=self.transcriber.model_name,
            first_segment_sequence_num=0,  # Placeholder, will be updated
            last_segment_sequence_num=-1,  # Placeholder, indicates no segments yet
            prompt="Whisper transcription job",  # Standardized prompt for Whisper calls
            status="pending",
        )
        try:
            self.db_session.add(current_whisper_call)
            self.db_session.commit()
        except IntegrityError:
            # Another process/thread created the same unique ModelCall concurrently
            self.db_session.rollback()
            current_whisper_call = (
                self.model_call_query.filter_by(
                    post_id=post.id,
                    model_name=self.transcriber.model_name,
                    first_segment_sequence_num=0,
                    last_segment_sequence_num=-1,
                )
                .order_by(ModelCall.timestamp.desc())
                .first()
            )
            if not current_whisper_call:
                # If not found despite conflict, re-raise
                raise

        self.logger.info(
            f"Created new Whisper ModelCall {current_whisper_call.id} for post {post.id}."
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        )

        try:
            self.logger.info(
<<<<<<< HEAD
                f"[TRANSCRIBE_START] Calling transcriber {self.transcriber.model_name} for post {post.id}, audio: {post.unprocessed_audio_path}"
            )
            # Expire session state before long-running transcription to avoid stale locks
            self.db_session.expire_all()

            pydantic_segments = self.transcriber.transcribe(post.unprocessed_audio_path)
            self.logger.info(
                f"[TRANSCRIBE_COMPLETE] Transcription by {self.transcriber.model_name} for post {post.id} resulted in {len(pydantic_segments)} segments."
            )

            segments_payload = [
                {
                    "sequence_num": i,
                    "start_time": round(seg.start, 1),
                    "end_time": round(seg.end, 1),
                    "text": seg.text,
                }
                for i, seg in enumerate(pydantic_segments or [])
            ]

            write_res = writer_client.action(
                "replace_transcription",
                {
                    "post_id": post.id,
                    "segments": segments_payload,
                    "model_call_id": current_whisper_call.id,
                },
                wait=True,
            )
            if not write_res or not write_res.success:
                raise RuntimeError(
                    getattr(write_res, "error", "Failed to persist transcription")
                )

            segment_query = (
                self.segment_query
                if self._segment_query_provided
                else self.db_session.query(TranscriptSegment)
            )
            db_segments: list[TranscriptSegment] = (
                segment_query.filter_by(post_id=post.id)
                .order_by(TranscriptSegment.sequence_num)
                .all()
            )
            self.logger.info(
                f"Successfully stored {len(db_segments)} transcript segments and updated ModelCall {current_whisper_call.id} for post {post.id}."
            )
            return db_segments
=======
                f"Calling transcriber {self.transcriber.model_name} for post {post.id}..."
            )
            pydantic_segments = self.transcriber.transcribe(post.unprocessed_audio_path)
            self.logger.info(
                f"Transcription by {self.transcriber.model_name} for post {post.id} resulted in {len(pydantic_segments)} segments."
            )

            self._delete_existing_segments_for_post(post.id)

            db_transcript_segments = self._persist_segments(post.id, pydantic_segments)

            # Update ModelCall with success status and details
            current_whisper_call.first_segment_sequence_num = 0
            current_whisper_call.last_segment_sequence_num = (
                len(db_transcript_segments) - 1
            )
            current_whisper_call.response = (
                f"{len(db_transcript_segments)} segments transcribed."
            )
            current_whisper_call.status = "success"

            self.db_session.commit()
            self.logger.info(
                f"Successfully stored {len(db_transcript_segments)} transcript segments and updated ModelCall {current_whisper_call.id} for post {post.id}."
            )
            return db_transcript_segments
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

        except Exception as e:
            self.logger.error(
                f"Transcription failed for post {post.id} using {self.transcriber.model_name}. Error: {e}",
                exc_info=True,
            )
<<<<<<< HEAD

            fail_res = writer_client.action(
                "mark_model_call_failed",
                {
                    "model_call_id": current_whisper_call.id,
                    "error_message": str(e),
                    "status": "failed_permanent",
                },
                wait=True,
            )
            if not fail_res or not fail_res.success:
                self.logger.error(
                    "Failed to mark ModelCall %s as failed via writer: %s",
                    current_whisper_call.id,
                    getattr(fail_res, "error", None),
                )

            raise
=======
            self.db_session.rollback()  # Rollback any potential partial additions from the try block

            # Re-fetch the ModelCall using THIS session to avoid cross-session conflicts
            call_to_update = (
                self.db_session.query(ModelCall).get(current_whisper_call.id)
                if current_whisper_call.id
                else None
            )
            if call_to_update:
                call_to_update.status = "failed_permanent"
                call_to_update.error_message = str(e)
                self.db_session.commit()
                self.logger.info(
                    f"Updated ModelCall {call_to_update.id} to status 'failed_permanent' for post {post.id}."
                )
            else:
                # This case should be rare if the initial commit of pending status was successful.
                self.logger.error(
                    f"Could not find ModelCall to update failure status for post {post.id} after transcription error."
                )

            raise

    # ------------------------ Internal helpers ------------------------
    def _delete_existing_segments_for_post(self, post_id: int) -> None:
        """Delete existing transcript segments and their identifications for a post."""
        existing_segment_ids = [
            row[0]
            for row in self.db_session.query(TranscriptSegment.id)
            .filter_by(post_id=post_id)
            .all()
        ]
        if not existing_segment_ids:
            return
        # Delete identifications that reference existing segments
        self.db_session.query(Identification).filter(
            Identification.transcript_segment_id.in_(existing_segment_ids)
        ).delete(synchronize_session=False)
        # Delete existing transcript segments
        self.segment_query.filter_by(post_id=post_id).delete(synchronize_session=False)
        self.db_session.flush()

    def _persist_segments(
        self, post_id: int, pydantic_segments: List[Any]
    ) -> List[TranscriptSegment]:
        """Persist pydantic segments to DB and return created ORM objects."""
        db_transcript_segments: List[TranscriptSegment] = []
        for i, segment_data in enumerate(pydantic_segments or []):
            start_time = round(segment_data.start, 1)
            end_time = round(segment_data.end, 1)
            db_segment = TranscriptSegment(
                post_id=post_id,
                sequence_num=i,
                start_time=start_time,
                end_time=end_time,
                text=segment_data.text,
            )
            db_transcript_segments.append(db_segment)
        if db_transcript_segments:
            self.db_session.add_all(db_transcript_segments)
        return db_transcript_segments
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
