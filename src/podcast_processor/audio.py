import logging
import math
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ffmpeg
import mutagen
from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TSSE,
    WXXX,
    ID3NoHeaderError,
)

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


def _clip_segments_complex(
    ad_segments_ms: list[tuple[int, int]],
    fade_ms: int,
    in_path: str,
    out_path: str,
    audio_duration_ms: int,
    encoding_args: dict[str, Any],
) -> None:
    """Original complex approach with fades."""

    trimmed_list = []

    last_end = 0
    for start_ms, end_ms in ad_segments_ms:
        trimmed_list.extend(
            [
                ffmpeg.input(in_path).filter(
                    "atrim", start=last_end / 1000.0, end=start_ms / 1000.0
                ),
                ffmpeg.input(in_path)
                .filter(
                    "atrim", start=start_ms / 1000.0, end=(start_ms + fade_ms) / 1000.0
                )
                .filter("afade", t="out", ss=0, d=fade_ms / 1000.0),
                ffmpeg.input(in_path)
                .filter("atrim", start=(end_ms - fade_ms) / 1000.0, end=end_ms / 1000.0)
                .filter("afade", t="in", ss=0, d=fade_ms / 1000.0),
            ]
        )

        last_end = end_ms

    if last_end != audio_duration_ms:
        trimmed_list.append(
            ffmpeg.input(in_path).filter(
                "atrim", start=last_end / 1000.0, end=audio_duration_ms / 1000.0
            )
        )

    logger.info(
        "[FFMPEG_CONCAT] Starting audio concatenation: %s -> %s (%d segments)",
        in_path,
        out_path,
        len(trimmed_list),
    )
    (
        ffmpeg.concat(*trimmed_list, v=0, a=1)
        .output(out_path, acodec="libmp3lame", **encoding_args)
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


def _clip_segments_simple(
    ad_segments_ms: list[tuple[int, int]],
    in_path: str,
    out_path: str,
    audio_duration_ms: int,
    encoding_args: dict[str, Any],
) -> None:
    """Simpler approach without fades - more reliable for many segments."""

    # Build list of segments to keep (inverse of ad segments)
    keep_segments: list[tuple[int, int]] = []
    last_end = 0

    for start_ms, end_ms in ad_segments_ms:
        if start_ms > last_end:
            keep_segments.append((last_end, start_ms))
        last_end = end_ms

    if last_end < audio_duration_ms:
        keep_segments.append((last_end, audio_duration_ms))

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


def trim_file(in_path: Path, out_path: Path, start_ms: int, end_ms: int) -> None:
    duration_ms = end_ms - start_ms

    if duration_ms <= 0:
        return

    start_sec = max(start_ms, 0) / 1000.0
    duration_sec = duration_ms / 1000.0

    logger.debug(
        "[FFMPEG_TRIM] Trimming %s -> %s (start=%.2fs, duration=%.2fs)",
        in_path,
        out_path,
        start_sec,
        duration_sec,
    )
    (
        ffmpeg.input(str(in_path))
        .output(
            str(out_path),
            ss=start_sec,
            t=duration_sec,
            acodec="copy",
            vn=None,
        )
        .overwrite_output()
        .run()
    )


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


# Frames where the source value is stale after re-encode. Source-side strings.
_SKIP_FRAMES = frozenset({"TLEN", "TSSE"})

# Cover-art bytes come back with this MIME, hard-capped to keep processing fast.
_COVER_MAX_BYTES = 2_000_000
_COVER_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class MetadataFallback:
    """Defaults used to fill ID3 frames the source MP3 is missing.

    All fields are optional; only set frames actually overwrite src tags.
    Build from Post + Feed rows via `fallback_for_post`.
    """

    title: str | None = None  # TIT2
    artist: str | None = None  # TPE1
    album: str | None = None  # TALB
    year: str | None = None  # TDRC
    comment: str | None = None  # COMM
    cover_url: str | None = None  # APIC (downloaded on the fly)
    url: str | None = None  # WXXX
    genre: str | None = None  # TCON


def fallback_for_post(
    *,
    post_title: str | None = None,
    post_description: str | None = None,
    post_release_date: Any = None,
    post_image_url: str | None = None,
    post_download_url: str | None = None,
    feed_title: str | None = None,
    feed_author: str | None = None,
    feed_image_url: str | None = None,
    genre: str = "Podcast",
) -> MetadataFallback:
    """Build a MetadataFallback from raw Post + Feed fields.

    ORM-free by design; callers pass scalars (Post.title, Feed.image_url, ...).
    Lets audio.py stay decoupled from app.models.
    """
    year: str | None = None
    if post_release_date is not None:
        try:
            year = str(post_release_date.year)
        except AttributeError:
            year = str(post_release_date)[:4]

    return MetadataFallback(
        title=post_title,
        artist=feed_author or feed_title,
        album=feed_title,
        year=year,
        comment=post_description,
        cover_url=post_image_url or feed_image_url,
        url=post_download_url,
        genre=genre,
    )


def _frame_text(frame: Any) -> list[Any]:
    # Note: types are relaxed from list[str] because some frames (TDRC, TYER)
    # yield mutagen's ID3TimeStamp objects which str-compare equal but are not
    # str instances; beartype's runtime check would reject those.
    return list(getattr(frame, "text", []) or [])


def _is_effectively_empty(text: list[Any]) -> bool:
    return not text or all(not str(t).strip() for t in text)


def _missing(dst: ID3, frame_id: str) -> bool:
    frames = dst.getall(frame_id)
    if not frames:
        return True
    return _is_effectively_empty(_frame_text(frames[0]))


def _fetch_cover(url: str) -> tuple[bytes, str] | None:
    """Download cover art. Returns (bytes, mime) or None on any failure."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Podly/1.0 (+metadata-fetch)"}
        )
        with urllib.request.urlopen(req, timeout=_COVER_TIMEOUT_S) as resp:
            data = resp.read(_COVER_MAX_BYTES)
            mime = resp.headers.get_content_type() or "image/jpeg"
            if not mime.startswith("image/"):
                return None
            return data, mime
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        logger.warning("[METADATA] Cover fetch failed for %s: %s", url, e)
        return None


def _apply_fallback(dst: ID3, fallback: MetadataFallback) -> dict[str, str]:
    """Fill missing ID3 frames from `fallback`. Returns map of frame_id -> source."""
    filled: dict[str, str] = {}

    if fallback.title and _missing(dst, "TIT2"):
        dst.delall("TIT2")
        dst.add(TIT2(encoding=3, text=[fallback.title[:128]]))
        filled["TIT2"] = "db"

    if fallback.artist and _missing(dst, "TPE1"):
        dst.delall("TPE1")
        dst.add(TPE1(encoding=3, text=[fallback.artist]))
        filled["TPE1"] = "db"

    if fallback.album and _missing(dst, "TALB"):
        dst.delall("TALB")
        dst.add(TALB(encoding=3, text=[fallback.album]))
        filled["TALB"] = "db"

    if fallback.year and _missing(dst, "TDRC"):
        dst.delall("TDRC")
        dst.add(TDRC(encoding=3, text=[fallback.year]))
        filled["TDRC"] = "db"

    if fallback.genre and _missing(dst, "TCON"):
        dst.delall("TCON")
        dst.add(TCON(encoding=3, text=[fallback.genre]))
        filled["TCON"] = "db"

    if fallback.comment and _missing(dst, "COMM"):
        dst.add(
            COMM(
                encoding=3,
                lang="eng",
                desc="",
                text=[fallback.comment[:1000]],
            )
        )
        filled["COMM"] = "db"

    if fallback.url and _missing(dst, "WXXX"):
        dst.add(WXXX(encoding=3, url=fallback.url))
        filled["WXXX"] = "db"

    if not dst.getall("APIC") and fallback.cover_url:
        data_mime = _fetch_cover(fallback.cover_url)
        if data_mime is not None:
            data, mime = data_mime
            dst.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
            filled["APIC"] = "db"

    return filled


def copy_metadata(
    in_path: str,
    out_path: str,
    *,
    fallback: MetadataFallback | None = None,
) -> None:
    """
    Copy ID3 tags (artist, title, album, cover art, ...) from in_path to out_path.

    ffmpeg re-encode with acodec=libmp3lame drops all ID3 tags; this restores
    them so podcast apps display the episode metadata correctly. Call right
    after clip_segments_with_fade or clip_segments_exact writes the output.

    Frames intentionally dropped / rewritten:
      - TLEN (length) -- the audio length changed after the cut.
      - TSSE (encoder) -- replaced with "Podly" so players attribute the
        re-encode to this pipeline, not to Lavf / iTunes / etc.

    Frames missing-or-empty in the source are filled from `fallback`
    (typically built from the Post + Feed DB rows via fallback_for_post).
    Source frames that already have a value are NOT overwritten.
    """
    try:
        src = ID3(in_path)
    except (ID3NoHeaderError, mutagen.MutagenError):
        src = None

    try:
        dst = ID3(out_path)
    except ID3NoHeaderError:
        dst = ID3()
    except mutagen.MutagenError as e:
        logger.warning("[METADATA] Failed to read existing tags on %s: %s", out_path, e)
        return

    copied: list[str] = []
    if src:
        for key, frame in src.items():
            if key in _SKIP_FRAMES:
                continue
            dst.add(frame)
            copied.append(key)

    # Provenance: this re-encode was done by Podly.
    dst.delall("TSSE")
    dst.add(TSSE(encoding=3, text=["Podly"]))

    filled: dict[str, str] = {}
    if fallback is not None:
        filled = _apply_fallback(dst, fallback)

    try:
        dst.save(out_path, v2_version=3)
        logger.info(
            "[METADATA] Restored %d src frame(s) on %s, %d from db (incl. APIC=%s)",
            len(copied),
            out_path,
            len(filled),
            "APIC" in copied or "APIC" in filled,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[METADATA] Failed to save tags on %s: %s", out_path, e)
