import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import ffmpeg

logger = logging.getLogger("global_logger")


def get_audio_duration_ms(file_path: str) -> int | None:
    try:
        logger.debug("[FFMPEG_PROBE] Probing audio file: %s", file_path)
        probe = ffmpeg.probe(file_path)
        format_info = probe["format"]
        duration_seconds = float(format_info["duration"])
        duration_milliseconds = duration_seconds * 1000
        logger.debug("[FFMPEG_PROBE] Duration: %.2f seconds", duration_seconds)
        return int(duration_milliseconds)
    except ffmpeg.Error as e:
        logger.error(
            "[FFMPEG_PROBE] Error probing file %s: %s",
            file_path,
            e.stderr.decode() if e.stderr else str(e),
        )
        return None


def _get_encoding_args(
    use_vbr: bool = False, vbr_quality: int = 2, cbr_bitrate: str = "192k"
) -> dict[str, Any]:
    """Return ffmpeg encoding arguments for VBR or CBR."""
    if use_vbr:
        return {"q:a": vbr_quality}
    return {"b:a": cbr_bitrate}


def clip_segments_with_fade(
    ad_segments_ms: list[tuple[int, int]],
    fade_ms: int,
    in_path: str,
    out_path: str,
    use_vbr: bool = False,
    vbr_quality: int = 2,
    cbr_bitrate: str = "192k",
) -> None:

    audio_duration_ms = get_audio_duration_ms(in_path)
    assert audio_duration_ms is not None

    encoding_args = _get_encoding_args(use_vbr, vbr_quality, cbr_bitrate)

    # Try the complex filter approach first, fall back to simple if it fails
    # Catch both ffmpeg.Error (runtime) and broader exceptions (filter graph construction)
    try:
        _clip_segments_complex(
            ad_segments_ms, fade_ms, in_path, out_path, audio_duration_ms, encoding_args
        )
    except ffmpeg.Error as e:
        err_msg = e.stderr.decode() if getattr(e, "stderr", None) else str(e)
        logger.warning(
            "Complex filter failed (ffmpeg error), trying simple approach: %s", err_msg
        )
        _clip_segments_simple(
            ad_segments_ms, in_path, out_path, audio_duration_ms, encoding_args
        )
    except Exception as e:  # noqa: BLE001
        # Catches filter graph construction errors like "multiple outgoing edges"
        logger.warning(
            "Complex filter failed (graph error), trying simple approach: %s", e
        )
        _clip_segments_simple(
            ad_segments_ms, in_path, out_path, audio_duration_ms, encoding_args
        )


def _keep_ranges(
    ad_segments_ms: list[tuple[int, int]], audio_duration_ms: int
) -> list[tuple[int, int]]:
    """Return content windows to keep (inverse of merged ad ranges)."""
    keep: list[tuple[int, int]] = []
    last_end = 0
    for start_ms, end_ms in ad_segments_ms:
        if end_ms < start_ms:
            continue
        if start_ms > last_end:
            keep.append((last_end, start_ms))
        last_end = max(last_end, end_ms)
    if last_end < audio_duration_ms:
        keep.append((last_end, audio_duration_ms))
    return keep


def _clip_segments_complex(
    ad_segments_ms: list[tuple[int, int]],
    fade_ms: int,
    in_path: str,
    out_path: str,
    audio_duration_ms: int,
    encoding_args: dict[str, Any],
) -> None:
    """Cut ads and fade the kept content edges. Never re-insert ad audio.

    Previous behavior faded the first/last `fade_ms` of each *ad* window, so a
    preroll starting at t=0 still opened with the DAI cold-open. Fades now apply
    only to retained content (fade-out before a cut, fade-in after one).
    """
    keep_segments = _keep_ranges(ad_segments_ms, audio_duration_ms)
    if not keep_segments:
        raise ValueError("No audio segments to keep after ad removal")

    trimmed_list = []
    for kstart, kend in keep_segments:
        duration_ms = kend - kstart
        if duration_ms <= 0:
            continue
        clip = (
            ffmpeg.input(in_path)
            .filter("atrim", start=kstart / 1000.0, end=kend / 1000.0)
            .filter("asetpts", "PTS-STARTPTS")
        )
        wants_fade_in = kstart > 0 and fade_ms > 0
        wants_fade_out = kend < audio_duration_ms and fade_ms > 0
        fade_in_ms = min(fade_ms, duration_ms) if wants_fade_in else 0
        fade_out_ms = min(fade_ms, duration_ms) if wants_fade_out else 0
        if fade_in_ms + fade_out_ms > duration_ms:
            fade_in_ms = duration_ms // 2 if wants_fade_in else 0
            fade_out_ms = (duration_ms - fade_in_ms) if wants_fade_out else 0
        if fade_in_ms > 0:
            clip = clip.filter("afade", t="in", st=0, d=fade_in_ms / 1000.0)
        if fade_out_ms > 0:
            clip = clip.filter(
                "afade",
                t="out",
                st=(duration_ms - fade_out_ms) / 1000.0,
                d=fade_out_ms / 1000.0,
            )
        trimmed_list.append(clip)

    if not trimmed_list:
        raise ValueError("No audio segments to keep after ad removal")

    logger.info(
        "[FFMPEG_CONCAT] Starting audio concatenation: %s -> %s (%d segments)",
        in_path,
        out_path,
        len(trimmed_list),
    )
    stream = (
        trimmed_list[0]
        if len(trimmed_list) == 1
        else ffmpeg.concat(*trimmed_list, v=0, a=1)
    )
    (
        stream.output(out_path, acodec="libmp3lame", **encoding_args)
        .overwrite_output()
        .run()
    )
    logger.info("[FFMPEG_CONCAT] Completed audio concatenation: %s", out_path)


def clip_segments_exact(
    ad_segments_ms: list[tuple[int, int]],
    in_path: str,
    out_path: str,
    cbr_bitrate: str = "192k",
) -> None:
    """Remove segments with exact cuts at boundaries, no fades.

    Used by chapter-based ad detection. Always uses CBR encoding because VBR
    causes seeking inaccuracy with chapter markers.
    """
    audio_duration_ms = get_audio_duration_ms(in_path)
    assert audio_duration_ms is not None
    # Chapter strategy always uses CBR for accurate chapter marker seeking
    encoding_args = _get_encoding_args(use_vbr=False, cbr_bitrate=cbr_bitrate)
    _clip_segments_simple(
        ad_segments_ms, in_path, out_path, audio_duration_ms, encoding_args
    )


def prepend_clip(clip_path: str, in_path: str, out_path: str) -> None:
    """Write clip followed by the full audio of in_path to out_path as MP3.

    The clip is converted to the sample rate and channel count of in_path, so
    the episode keeps its format. Chapters are dropped because their times no
    longer match; other metadata of in_path is kept.
    """
    sample_rate, channels = _audio_stream_format(in_path)
    channel_layout = "mono" if channels == 1 else "stereo"

    def _normalized(path: str) -> Any:
        return (
            ffmpeg.input(path)
            .audio.filter("aresample", sample_rate)
            .filter(
                "aformat",
                sample_fmts="fltp",
                sample_rates=sample_rate,
                channel_layouts=channel_layout,
            )
        )

    logger.info(
        "[FFMPEG_CONCAT] Prepending %s to %s -> %s", clip_path, in_path, out_path
    )
    (
        ffmpeg.concat(_normalized(clip_path), _normalized(in_path), v=0, a=1)
        .output(
            out_path,
            format="mp3",
            acodec="libmp3lame",
            map_metadata=1,
            map_chapters=-1,
            **_get_encoding_args(use_vbr=True),
        )
        .overwrite_output()
        .run()
    )


def _audio_stream_format(in_path: str) -> tuple[int, int]:
    """Return (sample_rate, channels) of the first audio stream of in_path."""
    probe = ffmpeg.probe(in_path)
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "audio":
            return int(stream["sample_rate"]), int(stream.get("channels") or 2)
    raise ValueError(f"No audio stream in {in_path}")


def _clip_segments_simple(
    ad_segments_ms: list[tuple[int, int]],
    in_path: str,
    out_path: str,
    audio_duration_ms: int,
    encoding_args: dict[str, Any],
) -> None:
    """Simpler approach without fades - more reliable for many segments."""

    keep_segments = _keep_ranges(ad_segments_ms, audio_duration_ms)

    if not keep_segments:
        raise ValueError("No audio segments to keep after ad removal")

    logger.info(
        "[FFMPEG_SIMPLE] Starting simple concat with %d segments", len(keep_segments)
    )

    # Create temp directory for intermediate files
    with tempfile.TemporaryDirectory() as temp_dir:
        segment_files = []

        # Extract each segment to keep
        for i, (start_ms, end_ms) in enumerate(keep_segments):
            segment_path = os.path.join(temp_dir, f"segment_{i}.mp3")
            start_sec = start_ms / 1000.0
            duration_sec = (end_ms - start_ms) / 1000.0

            (
                ffmpeg.input(in_path)
                .output(
                    segment_path,
                    ss=start_sec,
                    t=duration_sec,
                    acodec="libmp3lame",
                    **encoding_args,
                )
                .overwrite_output()
                .run(quiet=True)
            )

            segment_files.append(segment_path)

        # Create concat file list
        concat_list_path = os.path.join(temp_dir, "concat_list.txt")
        with open(concat_list_path, "w", encoding="utf-8") as file_list:
            for seg_file in segment_files:
                file_list.write(f"file '{seg_file}'\n")

        # Concatenate all segments
        (
            ffmpeg.input(concat_list_path, format="concat", safe=0)
            .output(out_path, acodec="libmp3lame", **encoding_args)
            .overwrite_output()
            .run(quiet=True)
        )

    logger.info("[FFMPEG_SIMPLE] Completed simple audio concatenation: %s", out_path)


def _input_codec_info(in_path: str) -> tuple[str, str]:
    """Return (codec_name, container_extension) for the first audio stream.

    Examples: ("mp3", ".mp3"), ("aac", ".m4a"), ("opus", ".opus").
    Falls back to ("unknown", ".mp3") if probing fails.
    """
    EXT_MAP = {"mp3": ".mp3", "aac": ".m4a", "opus": ".opus", "flac": ".flac"}
    try:
        probe = ffmpeg.probe(in_path)
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "audio":
                codec = stream.get("codec_name", "unknown")
                return (codec, EXT_MAP.get(codec, ".mp3"))
    except ffmpeg.Error:
        pass
    return ("unknown", ".mp3")


def trim_file(in_path: Path, out_path: Path, start_ms: int, end_ms: int) -> Path:
    """Trim *in_path* and write to *out_path*, remuxing (no re-encode).

    If the input codec cannot be muxed into the output container implied by
    *out_path* extension (e.g. AAC -> .mp3), the file is written with the
    correct extension and renamed.  Returns the actual output path.
    """
    duration_ms = end_ms - start_ms

    if duration_ms <= 0:
        return out_path

    start_sec = max(start_ms, 0) / 1000.0
    duration_sec = duration_ms / 1000.0

    codec, ext = _input_codec_info(str(in_path))
    needs_rename = ext != out_path.suffix

    # If codec/container mismatch, use the correct extension
    actual_out = out_path.with_suffix(ext) if needs_rename else out_path

    logger.debug(
        "[FFMPEG_TRIM] Trimming %s -> %s (start=%.2fs, duration=%.2fs, codec=%s, copy)",
        in_path,
        actual_out,
        start_sec,
        duration_sec,
        codec,
    )
    (
        ffmpeg.input(str(in_path))
        .output(
            str(actual_out),
            ss=start_sec,
            t=duration_sec,
            acodec="copy",
            vn=None,
        )
        .overwrite_output()
        .run()
    )

    # Rename to requested path if we used a different extension
    if needs_rename and actual_out != out_path:
        actual_out.rename(out_path)
        return out_path

    return actual_out


def split_audio(
    audio_file_path: Path,
    audio_chunk_path: Path,
    chunk_size_bytes: int,
) -> list[tuple[Path, int]]:

    audio_chunk_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "[FFMPEG_SPLIT] Splitting audio file: %s into chunks of %d bytes",
        audio_file_path,
        chunk_size_bytes,
    )
    duration_ms = get_audio_duration_ms(str(audio_file_path))
    assert duration_ms is not None
    if chunk_size_bytes <= 0:
        raise ValueError("chunk_size_bytes must be a positive integer")

    file_size_bytes = audio_file_path.stat().st_size
    if file_size_bytes == 0:
        raise ValueError("Cannot split zero-byte audio file")

    chunk_ratio = chunk_size_bytes / file_size_bytes
    chunk_duration_ms = max(1, math.ceil(duration_ms * chunk_ratio))

    num_chunks = max(1, math.ceil(duration_ms / chunk_duration_ms))
    logger.info(
        "[FFMPEG_SPLIT] Will create %d chunks (duration per chunk: %d ms)",
        num_chunks,
        chunk_duration_ms,
    )

    chunks: list[tuple[Path, int]] = []

    for i in range(num_chunks):
        start_offset_ms = i * chunk_duration_ms
        if start_offset_ms >= duration_ms:
            break

        end_offset_ms = min(duration_ms, (i + 1) * chunk_duration_ms)

        export_path = audio_chunk_path / f"{i}.mp3"
        logger.debug(
            "[FFMPEG_SPLIT] Creating chunk %d/%d: %s", i + 1, num_chunks, export_path
        )
        trim_file(audio_file_path, export_path, start_offset_ms, end_offset_ms)
        chunks.append((export_path, start_offset_ms))

    logger.info("[FFMPEG_SPLIT] Split complete: created %d chunks", len(chunks))
    return chunks
