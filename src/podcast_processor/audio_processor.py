import logging
<<<<<<< HEAD
from typing import Any

from app.extensions import db
from app.models import Identification, ModelCall, Post, TranscriptSegment
from app.writer.client import writer_client
from podcast_processor.ad_merger import AdMerger
=======
from typing import Any, List, Optional, Tuple

from app.extensions import db
from app.models import (
    Identification,
    ModelCall,
    Post,
    ProcessingStatistics,
    PromptPreset,
    TranscriptSegment,
)
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
from podcast_processor.audio import clip_segments_with_fade, get_audio_duration_ms
from shared.config import Config


class AudioProcessor:
    """Handles audio processing and ad segment removal from podcast files."""

    def __init__(
        self,
        config: Config,
<<<<<<< HEAD
        logger: logging.Logger | None = None,
        identification_query: Any | None = None,
        transcript_segment_query: Any | None = None,
        model_call_query: Any | None = None,
        db_session: Any | None = None,
    ):
        self.logger = logger or logging.getLogger("global_logger")
        self.config = config
        self._identification_query_provided = identification_query is not None
=======
        logger: Optional[logging.Logger] = None,
        identification_query: Optional[Any] = None,
        transcript_segment_query: Optional[Any] = None,
        model_call_query: Optional[Any] = None,
        db_session: Optional[Any] = None,
    ):
        self.logger = logger or logging.getLogger("global_logger")
        self.config = config
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        self.identification_query = identification_query or Identification.query
        self.transcript_segment_query = (
            transcript_segment_query or TranscriptSegment.query
        )
        self.model_call_query = model_call_query or ModelCall.query
        self.db_session = db_session or db.session
<<<<<<< HEAD
        self.ad_merger = AdMerger()

    def get_ad_segments(self, post: Post) -> list[tuple[float, float]]:
        """
        Retrieves ad segments from the database for a given post.

        NOTE: Uses self.db_session.query() instead of self.identification_query
        to ensure all operations use the same session consistently.

=======

    def get_ad_segments(self, post: Post) -> List[Tuple[float, float]]:
        """
        Retrieves ad segments from the database for a given post.

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        Args:
            post: The Post object to retrieve ad segments for

        Returns:
            A list of tuples containing start and end times (in seconds) of ad segments
        """
        self.logger.info(f"Retrieving ad segments from database for post {post.id}.")

<<<<<<< HEAD
        query = (
            self.identification_query
            if self._identification_query_provided
            else self.db_session.query(Identification)
        )

        ad_identifications = (
            query.join(
=======
        refined_segments = self._get_refined_ad_segments(post)
        if refined_segments:
            self.logger.info(
                "Using %s refined ad boundaries for post %s.",
                len(refined_segments),
                post.id,
            )
            return refined_segments

        ad_identifications = (
            self.identification_query.join(
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
                TranscriptSegment,
                Identification.transcript_segment_id == TranscriptSegment.id,
            )
            .join(ModelCall, Identification.model_call_id == ModelCall.id)
            .filter(
                TranscriptSegment.post_id == post.id,
                Identification.label == "ad",
                Identification.confidence >= self.config.output.min_confidence,
                ModelCall.status
                == "success",  # Only consider identifications from successful LLM calls
            )
            .all()
        )

        if not ad_identifications:
            self.logger.info(
                f"No ad segments found meeting criteria for post {post.id}."
            )
            return []

<<<<<<< HEAD
        # Get full segment objects with text for content analysis
        # Filter out any identifications with missing segments (DB integrity check)
        ad_segments_with_text = []
        valid_identifications = []
        for ident in ad_identifications:
            segment = ident.transcript_segment
            if segment:
                ad_segments_with_text.append(segment)
                valid_identifications.append(ident)
=======
        ad_segments_times: List[Tuple[float, float]] = []
        for ident in ad_identifications:
            segment = ident.transcript_segment  # Accessing via backref
            if segment:
                ad_segments_times.append((segment.start_time, segment.end_time))
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
            else:
                # This should ideally not happen if DB integrity is maintained
                self.logger.warning(
                    f"Identification {ident.id} for post {post.id} refers to a missing TranscriptSegment {ident.transcript_segment_id}. Skipping."
                )

<<<<<<< HEAD
        if not ad_segments_with_text:
            self.logger.info(
                f"No valid ad segments with transcript data for post {post.id}."
            )
            return []

        # Content-aware merge
        ad_groups = self.ad_merger.merge(
            ad_segments=ad_segments_with_text,
            identifications=valid_identifications,
            max_gap=float(self.config.output.min_ad_segment_separation_seconds),
            min_content_gap=12.0,
        )

        # If boundary refinement persisted refined windows on the post, prefer those
        # refined timestamps for audio cutting (this allows word-level refinement to
        # affect the actual cut start time).
        if getattr(self.config, "enable_boundary_refinement", False):
            self._apply_refined_boundaries(post, ad_groups)

        self.logger.info(
            f"Merged {len(ad_segments_with_text)} segments into {len(ad_groups)} groups for post {post.id}"
        )

        # Convert to time tuples for merge_ad_segments()
        ad_segments_times = [(g.start_time, g.end_time) for g in ad_groups]
        ad_segments_times.sort(key=lambda x: x[0])
        return ad_segments_times

    def _apply_refined_boundaries(self, post: Post, ad_groups: Any) -> None:
        post_row = self._safe_get_post_row(post)
        refined = getattr(post_row, "refined_ad_boundaries", None) if post_row else None
        parsed = self._parse_refined_boundaries(refined)
        if not parsed:
            return

        for group in ad_groups:
            overlap_window = self._refined_overlap_window_for_group(group, parsed)
            if overlap_window is None:
                continue
            refined_start_min, refined_end_max = overlap_window

            new_start = max(group.start_time, refined_start_min)
            new_end = min(group.end_time, refined_end_max)
            if new_end > new_start:
                group.start_time = new_start
                group.end_time = new_end

    def _safe_get_post_row(self, post: Post) -> Post | None:
        try:
            return self.db_session.get(Post, post.id)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _parse_refined_boundaries(
        refined: Any,
    ) -> list[tuple[float, float, float, float]]:
        if not refined or not isinstance(refined, list):
            return []

        parsed: list[tuple[float, float, float, float]] = []
        for item in refined:
            if not isinstance(item, dict):
                continue

            orig_start_raw = item.get("orig_start")
            orig_end_raw = item.get("orig_end")
            refined_start_raw = item.get("refined_start")
            refined_end_raw = item.get("refined_end")
            if (
                orig_start_raw is None
                or orig_end_raw is None
                or refined_start_raw is None
                or refined_end_raw is None
            ):
                continue

            try:
                orig_start = float(orig_start_raw)
                orig_end = float(orig_end_raw)
                refined_start = float(refined_start_raw)
                refined_end = float(refined_end_raw)
            except Exception:  # noqa: BLE001
                continue

            if refined_end <= refined_start:
                continue

            parsed.append((orig_start, orig_end, refined_start, refined_end))

        return parsed

    @staticmethod
    def _refined_overlap_window_for_group(
        group: Any,
        parsed: list[tuple[float, float, float, float]],
    ) -> tuple[float, float] | None:
        overlaps: list[tuple[float, float]] = []
        for orig_start, orig_end, refined_start, refined_end in parsed:
            overlap = max(
                0.0,
                min(group.end_time, orig_end) - max(group.start_time, orig_start),
            )
            if overlap > 0.0:
                overlaps.append((refined_start, refined_end))

        if not overlaps:
            return None

        refined_start_min = min(s for s, _ in overlaps)
        refined_end_max = max(e for _, e in overlaps)
        return refined_start_min, refined_end_max
=======
        self.logger.info(
            f"Found {len(ad_segments_times)} ad segments for post {post.id} from database."
        )
        # Sort by start time, as processing might expect this order
        ad_segments_times.sort(key=lambda x: x[0])
        return ad_segments_times

    def _get_refined_ad_segments(self, post: Post) -> List[Tuple[float, float]]:
        if not getattr(self.config, "enable_boundary_refinement", False):
            return []

        raw_boundaries = getattr(post, "refined_ad_boundaries", None) or []
        if not isinstance(raw_boundaries, list):
            return []

        refined_segments: List[Tuple[float, float]] = []
        for item in raw_boundaries:
            if not isinstance(item, dict):
                continue
            start_raw = item.get("refined_start")
            end_raw = item.get("refined_end")
            if start_raw is None or end_raw is None:
                continue
            try:
                start = float(start_raw)
                end = float(end_raw)
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue
            refined_segments.append((start, end))

        refined_segments.sort(key=lambda segment: segment[0])
        return refined_segments
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

    def merge_ad_segments(
        self,
        *,
        duration_ms: int,
<<<<<<< HEAD
        ad_segments: list[tuple[float, float]],
        min_ad_segment_length_seconds: float,
        min_ad_segment_separation_seconds: float,
    ) -> list[tuple[int, int]]:
=======
        ad_segments: List[Tuple[float, float]],
        min_ad_segment_length_seconds: float,
        min_ad_segment_separation_seconds: float,
    ) -> List[Tuple[int, int]]:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        """
        Merges nearby ad segments and filters out segments that are too short.

        Args:
            duration_ms: Duration of the audio in milliseconds
            ad_segments: List of ad segments as (start, end) tuples in seconds
            min_ad_segment_length_seconds: Minimum length of an ad segment to retain
            min_ad_segment_separation_seconds: Minimum separation between segments before merging

        Returns:
            List of merged ad segments as (start, end) tuples in milliseconds
        """
        audio_duration_seconds = duration_ms / 1000.0

        self.logger.info(
            f"Creating new audio with ads segments removed between: {ad_segments}"
        )
<<<<<<< HEAD
        if not ad_segments:
            return []

        ad_segments = sorted(ad_segments)

        last_segment = self._get_last_segment_if_near_end(
            ad_segments,
            audio_duration_seconds=audio_duration_seconds,
            min_separation=min_ad_segment_separation_seconds,
        )

        ad_segments = self._merge_close_segments(
            ad_segments, min_separation=min_ad_segment_separation_seconds
        )
        ad_segments = self._filter_short_segments(
            ad_segments, min_length=min_ad_segment_length_seconds
        )
        ad_segments = self._restore_last_segment_if_needed(ad_segments, last_segment)
        ad_segments = self._extend_last_segment_to_end_if_needed(
            ad_segments,
            audio_duration_seconds=audio_duration_seconds,
            min_separation=min_ad_segment_separation_seconds,
        )

        self.logger.info(f"Joined ad segments into: {ad_segments}")
        return [(int(start * 1000), int(end * 1000)) for start, end in ad_segments]

    def _get_last_segment_if_near_end(
        self,
        ad_segments: list[tuple[float, float]],
        *,
        audio_duration_seconds: float,
        min_separation: float,
    ) -> tuple[float, float] | None:
        if not ad_segments:
            return None
        if (audio_duration_seconds - ad_segments[-1][1]) < min_separation:
            return ad_segments[-1]
        return None

    def _merge_close_segments(
        self,
        ad_segments: list[tuple[float, float]],
        *,
        min_separation: float,
    ) -> list[tuple[float, float]]:
        merged = list(ad_segments)
        i = 0
        while i < len(merged) - 1:
            if merged[i][1] + min_separation >= merged[i + 1][0]:
                merged[i] = (merged[i][0], merged[i + 1][1])
                merged.pop(i + 1)
            else:
                i += 1
        return merged

    def _filter_short_segments(
        self,
        ad_segments: list[tuple[float, float]],
        *,
        min_length: float,
    ) -> list[tuple[float, float]]:
        return [s for s in ad_segments if (s[1] - s[0]) >= min_length]

    def _restore_last_segment_if_needed(
        self,
        ad_segments: list[tuple[float, float]],
        last_segment: tuple[float, float] | None,
    ) -> list[tuple[float, float]]:
        if last_segment is None:
            return ad_segments
        if not ad_segments or ad_segments[-1] != last_segment:
            return [*ad_segments, last_segment]
        return ad_segments

    def _extend_last_segment_to_end_if_needed(
        self,
        ad_segments: list[tuple[float, float]],
        *,
        audio_duration_seconds: float,
        min_separation: float,
    ) -> list[tuple[float, float]]:
        if not ad_segments:
            return ad_segments
        if (audio_duration_seconds - ad_segments[-1][1]) < min_separation:
            return [*ad_segments[:-1], (ad_segments[-1][0], audio_duration_seconds)]
        return ad_segments

    def process_audio(self, post: Post, output_path: str) -> list[tuple[int, int]]:
=======
        # if no segments provided, return empty list
        if not ad_segments:
            return []

        # if any two ad segments overlap by fade_ms, join them into a single segment
        ad_segments = sorted(ad_segments)
        i = 0

        # Initialize variable for storing the last segment
        last_segment = None
        has_segment_near_end = False

        # Check for segments near the end before merging
        if len(ad_segments) > 0 and (
            audio_duration_seconds - ad_segments[-1][1]
            < min_ad_segment_separation_seconds
        ):
            # Save the last segment before filtering
            last_segment = ad_segments[-1]
            has_segment_near_end = True

        # Merge overlapping segments
        while i < len(ad_segments) - 1:
            if (
                ad_segments[i][1] + min_ad_segment_separation_seconds
                >= ad_segments[i + 1][0]
            ):
                ad_segments[i] = (ad_segments[i][0], ad_segments[i + 1][1])
                ad_segments.pop(i + 1)
            else:
                i += 1

        # remove any isolated ad segments that are too short, possibly misidentified
        ad_segments = [
            segment
            for segment in ad_segments
            if segment[1] - segment[0] >= min_ad_segment_length_seconds
        ]

        # Restore the last segment if it was near the end but got filtered out
        if (
            has_segment_near_end
            and last_segment is not None
            and (not ad_segments or ad_segments[-1] != last_segment)
        ):
            ad_segments.append(last_segment)

        # Extend the last segment to the end if it's near the end
        if len(ad_segments) > 0 and (
            audio_duration_seconds - ad_segments[-1][1]
            < min_ad_segment_separation_seconds
        ):
            ad_segments[-1] = (ad_segments[-1][0], audio_duration_seconds)

        self.logger.info(f"Joined ad segments into: {ad_segments}")

        ad_segments_ms = [
            (int(start * 1000), int(end * 1000)) for start, end in ad_segments
        ]
        return ad_segments_ms

    def process_audio(self, post: Post, output_path: str) -> None:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        """
        Process the podcast audio by removing ad segments.

        Args:
            post: The Post object containing the podcast to process
            output_path: Path where the processed audio file should be saved
<<<<<<< HEAD
        Returns:
            The merged ad segments that were removed, as millisecond windows.
=======
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        """
        ad_segments = self.get_ad_segments(post)

        duration_ms = get_audio_duration_ms(post.unprocessed_audio_path)
        if duration_ms is None:
            raise ValueError(
                f"Could not determine duration for audio: {post.unprocessed_audio_path}"
            )

<<<<<<< HEAD
=======
        # Store duration in seconds
        original_duration_seconds = duration_ms / 1000.0
        post.duration = original_duration_seconds

>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        merged_ad_segments = self.merge_ad_segments(
            duration_ms=duration_ms,
            ad_segments=ad_segments,
            min_ad_segment_length_seconds=float(
                self.config.output.min_ad_segment_length_seconds
            ),
            min_ad_segment_separation_seconds=float(
                self.config.output.min_ad_segement_separation_seconds
            ),
        )

<<<<<<< HEAD
        # LLM strategy doesn't use chapter markers, so VBR is fine for smaller files
=======
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        clip_segments_with_fade(
            in_path=post.unprocessed_audio_path,
            ad_segments_ms=merged_ad_segments,
            fade_ms=self.config.output.fade_ms,
            out_path=output_path,
<<<<<<< HEAD
            use_vbr=True,
        )

        processed_duration_ms = get_audio_duration_ms(output_path)
        if processed_duration_ms is None:
            self.logger.warning(
                "Could not determine processed audio duration for post %s at %s; "
                "falling back to source duration",
                post.id,
                output_path,
            )
            processed_duration_ms = duration_ms

        # Persist the final MP3 runtime so downstream RSS/stats reflect ad-removed
        # audio rather than the source episode length.
        post.duration = processed_duration_ms / 1000.0
        post.processed_audio_path = output_path
        result = writer_client.update(
            "Post",
            post.id,
            {"processed_audio_path": output_path, "duration": post.duration},
            wait=True,
        )
        if not result or not result.success:
            raise RuntimeError(getattr(result, "error", "Failed to update post"))
        try:
            self.db_session.expire(post)
        except Exception:  # noqa: BLE001
            pass
=======
        )

        post.processed_audio_path = output_path

        # Calculate and store processing statistics
        self._store_processing_statistics(
            post=post,
            original_duration_seconds=original_duration_seconds,
            merged_ad_segments_ms=merged_ad_segments,
        )

        self.db_session.commit()
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

        self.logger.info(
            f"Audio processing complete for post {post.id}, saved to {output_path}"
        )
<<<<<<< HEAD
        return merged_ad_segments
=======

    def _store_processing_statistics(
        self,
        post: Post,
        original_duration_seconds: float,
        merged_ad_segments_ms: List[Tuple[int, int]],
    ) -> None:
        """
        Calculate and store processing statistics for the episode.

        Args:
            post: The Post object being processed
            original_duration_seconds: Original duration before ad removal
            merged_ad_segments_ms: List of merged ad segments in milliseconds
        """
        # Calculate total duration removed
        total_duration_removed_ms = sum(
            end - start for start, end in merged_ad_segments_ms
        )
        total_duration_removed_seconds = total_duration_removed_ms / 1000.0

        # Calculate processed duration
        processed_duration_seconds = (
            original_duration_seconds - total_duration_removed_seconds
        )

        # Calculate percentage removed
        percentage_removed = (
            (total_duration_removed_seconds / original_duration_seconds * 100)
            if original_duration_seconds > 0
            else 0.0
        )

        prompt_preset_id = getattr(post, "processed_with_preset_id", None)
        if prompt_preset_id is None:
            active_preset = PromptPreset.query.filter_by(is_active=True).first()
            prompt_preset_id = active_preset.id if active_preset else None

        # Check if statistics already exist for this post
        existing_stats = ProcessingStatistics.query.filter_by(post_id=post.id).first()

        if existing_stats:
            # Update existing statistics
            existing_stats.total_ad_segments_removed = len(merged_ad_segments_ms)
            existing_stats.total_duration_removed_seconds = (
                total_duration_removed_seconds
            )
            existing_stats.original_duration_seconds = original_duration_seconds
            existing_stats.processed_duration_seconds = processed_duration_seconds
            existing_stats.percentage_removed = percentage_removed
            existing_stats.prompt_preset_id = prompt_preset_id
            self.logger.info(
                f"Updated statistics for post {post.id}: "
                f"{len(merged_ad_segments_ms)} segments, "
                f"{total_duration_removed_seconds:.1f}s removed ({percentage_removed:.1f}%)"
            )
        else:
            # Create new statistics
            stats = ProcessingStatistics(
                post_id=post.id,
                total_ad_segments_removed=len(merged_ad_segments_ms),
                total_duration_removed_seconds=total_duration_removed_seconds,
                original_duration_seconds=original_duration_seconds,
                processed_duration_seconds=processed_duration_seconds,
                percentage_removed=percentage_removed,
                prompt_preset_id=prompt_preset_id,
            )
            self.db_session.add(stats)
            self.logger.info(
                f"Created statistics for post {post.id}: "
                f"{len(merged_ad_segments_ms)} segments, "
                f"{total_duration_removed_seconds:.1f}s removed ({percentage_removed:.1f}%)"
            )
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
