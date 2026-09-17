"""Tests for copy_metadata + MetadataFallback (ID3 restoration + DB fallback).

The pipeline flow under test:
    src.mp3 (with ID3 tags) -> ffmpeg re-encode -> dst.mp3 (tags stripped)
    -> copy_metadata(src, dst[, fallback]) -> dst.mp3 (tags restored + filled)

ffmpeg re-encode is invoked here via ffmpeg-python with `map_metadata=-1` so
the test exercises the same metadata-stripping behaviour as the production
clip_segments_* helpers without depending on their Temp-dir plumbing.
"""

import datetime
import shutil
import time
from pathlib import Path

import ffmpeg
import pytest
from mutagen.id3 import (
    APIC,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TLEN,
    TPE1,
    TSSE,
)

from podcast_processor import audio
from podcast_processor.audio import (
    MetadataFallback,
    copy_metadata,
    fallback_for_post,
)

TEST_FILE = Path("src/tests/data/count_0_99.mp3")

# Smallest valid PNG (1x1 transparent). Re-used across APIC-related tests.
_PNG_1X1 = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000"
    "001F15C4890000000D49444154789C636060000000000400017A6E2C"
    "990000000049454E44AE426082"
)


# --------------------------- helpers --------------------------- #


def _reencode_stripping(in_path: Path, out_path: Path) -> None:
    """Re-encode audio (drops all ID3 tags) just like the production clippers do."""
    (
        ffmpeg.input(str(in_path))
        .output(
            str(out_path),
            acodec="libmp3lame",
            q=2,
            vn=None,
            map_metadata=-1,
        )
        .overwrite_output()
        .run(quiet=True)
    )


def _write_src_with_tags(src_path: Path, tags: ID3) -> None:
    """Seed src_path with the bundled audio + the supplied ID3 frames."""
    shutil.copy(TEST_FILE, src_path)
    tags.save(str(src_path), v2_version=3)
    # Brief sleep avoids Windows file-locking races between mutagen and ffmpeg.
    time.sleep(0.05)


# --------------------------- fixtures --------------------------- #


@pytest.fixture
def plain_src(tmp_path: Path) -> Path:
    """A source MP3 with NO ID3 tags (only the source file's raw bytes)."""
    p = tmp_path / "plain_src.mp3"
    shutil.copy(TEST_FILE, p)
    time.sleep(0.05)
    return p


@pytest.fixture
def src_with_full_tags(tmp_path: Path) -> Path:
    """A source MP3 carrying TIT2, TPE1, TALB, TCON, APIC, TLEN, TSSE.
    TDRC is intentionally omitted so the year fallback path can run.
    """
    tags = ID3()
    tags.add(TIT2(encoding=3, text=["Original Episode Title"]))
    tags.add(TPE1(encoding=3, text=["Original Artist"]))
    tags.add(TALB(encoding=3, text=["Original Podcast"]))
    tags.add(TCON(encoding=3, text=["Podcast"]))
    tags.add(TSSE(encoding=3, text=["Original Encoder"]))
    tags.add(TLEN(encoding=3, text=[66048]))
    tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=_PNG_1X1))
    p = tmp_path / "src_full.mp3"
    _write_src_with_tags(p, tags)
    return p


@pytest.fixture
def stripped_dst(tmp_path: Path, plain_src: Path) -> Path:
    """dst.mp3 produced from `plain_src` by an ffmpeg re-encode that drops tags."""
    dst = tmp_path / "dst.mp3"
    _reencode_stripping(plain_src, dst)
    return dst


# --------------------------- copy_metadata (no fallback) --------------------------- #


def test_copy_metadata_drops_tlen_when_present_in_src(tmp_path: Path) -> None:
    """TLEN (length) is stale after a re-encode and must never be propagated."""
    src_tags = ID3()
    src_tags.add(TIT2(encoding=3, text=["ep"]))
    src_tags.add(TLEN(encoding=3, text=[66048]))
    src = tmp_path / "src_with_tlen.mp3"
    _write_src_with_tags(src, src_tags)

    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src, dst)
    copy_metadata(in_path=str(src), out_path=str(dst))

    out = ID3(dst)
    assert "TLEN" not in out
    # Sanity: we did copy TIT2 through.
    assert out["TIT2"].text == ["ep"]


def test_copy_metadata_overwrites_tsse_with_podly(tmp_path: Path) -> None:
    """TSSE must be replaced with the literal string "Podly" on the output."""
    src_tags = ID3()
    src_tags.add(TSSE(encoding=3, text=["Lavc62.11.100 libmp3lame"]))
    src = tmp_path / "src_tsse.mp3"
    _write_src_with_tags(src, src_tags)

    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src, dst)
    copy_metadata(in_path=str(src), out_path=str(dst))

    out = ID3(dst)
    assert out["TSSE"].text == ["Podly"]


def test_copy_metadata_handles_source_without_id3_header(tmp_path: Path) -> None:
    """If the source has no ID3 frame at all, we must not crash and still set TSSE."""
    plain = tmp_path / "src.mp3"
    shutil.copy(TEST_FILE, plain)
    time.sleep(0.05)
    # Strip the ID3 header on src so src has no ID3 at all.
    raw = plain.read_bytes()
    if raw[:3] == b"ID3":
        size_bytes = raw[6:10]
        size = 0
        for byte in size_bytes:
            size = (size << 7) | byte
        tag_total = 10 + size
        plain.write_bytes(raw[tag_total:])
        assert not _has_id3_header(plain)

    dst = tmp_path / "dst.mp3"
    _reencode_stripping(plain, dst)
    copy_metadata(in_path=str(plain), out_path=str(dst))

    out = ID3(dst)
    assert out["TSSE"].text == ["Podly"]


def _has_id3_header(path: Path) -> bool:
    return Path(path).read_bytes()[:3] == b"ID3"


def test_copy_metadata_passes_full_tag_set_through(tmp_path: Path) -> None:
    """All non-skipped src frames must appear on dst verbatim."""
    src = tmp_path / "src_full.mp3"
    shutil.copy(TEST_FILE, src)
    src_tags = ID3()
    src_tags.add(TIT2(encoding=3, text=["Original Episode Title"]))
    src_tags.add(TPE1(encoding=3, text=["Original Artist"]))
    src_tags.add(TALB(encoding=3, text=["Original Podcast"]))
    src_tags.add(TDRC(encoding=3, text=["2025"]))
    src_tags.add(TCON(encoding=3, text=["Podcast"]))
    src_tags.add(TSSE(encoding=3, text=["Original Encoder"]))
    src_tags.add(
        APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=_PNG_1X1)
    )
    src_tags.save(str(src), v2_version=3)
    time.sleep(0.05)

    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src, dst)
    copy_metadata(in_path=str(src), out_path=str(dst))

    out = ID3(dst)
    assert out["TIT2"].text == ["Original Episode Title"]
    assert out["TPE1"].text == ["Original Artist"]
    assert out["TALB"].text == ["Original Podcast"]
    assert str(out["TDRC"]).strip() == "2025"
    assert out["TCON"].text == ["Podcast"]
    assert out["TSSE"].text == ["Podly"]
    apics = out.getall("APIC")
    assert len(apics) == 1
    assert apics[0].data == _PNG_1X1


def test_src_tdrc_is_preserved_when_present(tmp_path: Path) -> None:
    """TDRC from src must override the year fallback."""
    src_tags = ID3()
    src_tags.add(TDRC(encoding=3, text=["2024"]))
    src = tmp_path / "src_tdrc.mp3"
    _write_src_with_tags(src, src_tags)
    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src, dst)
    fb = MetadataFallback(year="2026")
    copy_metadata(in_path=str(src), out_path=str(dst), fallback=fb)
    out = ID3(dst)
    assert str(out["TDRC"]).strip() == "2024"


def test_copy_metadata_noop_for_unhappy_source(tmp_path: Path, monkeypatch) -> None:
    """A read failure on src should log and exit gracefully (no crash, no save)."""
    src = tmp_path / "does_not_exist.mp3"
    dst = tmp_path / "dst.mp3"
    shutil.copy(TEST_FILE, dst)
    # Should not raise; logging only.
    copy_metadata(in_path=str(src), out_path=str(dst))


# --------------------------- copy_metadata (with MetadataFallback) --------------------------- #


def test_fallback_fills_missing_text_frames(
    stripped_dst: Path, plain_src: Path
) -> None:
    fb = MetadataFallback(
        title="FB Episode",
        artist="FB Artist",
        album="FB Podcast",
        year="2026",
        comment="FB description",
        url="https://example.com/ep.mp3",
        genre="Podcast",
    )
    copy_metadata(in_path=str(plain_src), out_path=str(stripped_dst), fallback=fb)

    out = ID3(stripped_dst)
    assert out["TIT2"].text == ["FB Episode"]
    assert out["TPE1"].text == ["FB Artist"]
    assert out["TALB"].text == ["FB Podcast"]
    assert str(out["TDRC"]).strip() == "2026"
    assert out["TCON"].text == ["Podcast"]
    comms = out.getall("COMM")
    assert len(comms) == 1
    assert comms[0].text == ["FB description"]
    ws = out.getall("WXXX")
    assert len(ws) == 1
    assert ws[0].url == "https://example.com/ep.mp3"
    assert out["TSSE"].text == ["Podly"]


def test_fallback_does_not_overwrite_existing_frames(
    tmp_path: Path, src_with_full_tags: Path
) -> None:
    """Frames already present (and non-empty) in src must be preserved, not overwritten."""
    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src_with_full_tags, dst)

    fb = MetadataFallback(
        title="FB Title (should lose)",
        artist="FB Artist (should lose)",
        # The following are missing in src and should be filled.
        year="2026",
        genre="Podcast",
    )
    copy_metadata(
        in_path=str(src_with_full_tags),
        out_path=str(dst),
        fallback=fb,
    )

    out = ID3(dst)
    assert out["TIT2"].text == ["Original Episode Title"]
    assert out["TPE1"].text == ["Original Artist"]
    assert out["TALB"].text == ["Original Podcast"]
    # Filled because missing in src.
    assert str(out["TDRC"]).strip() == "2026"
    assert out["TCON"].text == ["Podcast"]


def test_fallback_downloads_cover_when_apic_missing(
    tmp_path: Path, monkeypatch
) -> None:
    src_tags = ID3()
    src_tags.add(TIT2(encoding=3, text=["ep"]))
    src = tmp_path / "src_no_apic.mp3"
    _write_src_with_tags(src, src_tags)

    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src, dst)

    captured: dict[str, str] = {}

    def fake_fetch(url: str) -> tuple[bytes, str] | None:
        captured["url"] = url
        return (_PNG_1X1, "image/png")

    monkeypatch.setattr(audio, "_fetch_cover", fake_fetch)

    fb = MetadataFallback(cover_url="https://example.com/cover.png")
    copy_metadata(in_path=str(src), out_path=str(dst), fallback=fb)

    assert captured.get("url") == "https://example.com/cover.png"
    out = ID3(dst)
    apics = out.getall("APIC")
    assert len(apics) == 1
    assert apics[0].data == _PNG_1X1
    assert apics[0].mime == "image/png"


def test_fallback_preserves_existing_apic_and_skips_download(
    tmp_path: Path, src_with_full_tags: Path, monkeypatch
) -> None:
    """If src already carries APIC, the network fetch must NOT run."""
    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src_with_full_tags, dst)

    def boom(url: str):
        raise AssertionError("download must not be called when src has APIC")

    monkeypatch.setattr(audio, "_fetch_cover", boom)

    copy_metadata(
        in_path=str(src_with_full_tags),
        out_path=str(dst),
        fallback=MetadataFallback(cover_url="https://example.com/should-not-fetch"),
    )
    out = ID3(dst)
    apics = out.getall("APIC")
    assert len(apics) == 1
    assert apics[0].data == _PNG_1X1


def test_fallback_skips_cover_when_fetch_fails(tmp_path: Path, monkeypatch) -> None:
    src_tags = ID3()
    src_tags.add(TIT2(encoding=3, text=["ep"]))
    src = tmp_path / "src_no_apic.mp3"
    _write_src_with_tags(src, src_tags)
    dst = tmp_path / "dst.mp3"
    _reencode_stripping(src, dst)

    monkeypatch.setattr(audio, "_fetch_cover", lambda url: None)

    fb = MetadataFallback(cover_url="https://broken.example.com/cover.png")
    copy_metadata(in_path=str(src), out_path=str(dst), fallback=fb)

    out = ID3(dst)
    assert "APIC" not in out  # no APIC frame
    assert out["TIT2"].text == ["ep"]


def test_fallback_with_none_is_a_noop(tmp_path: Path, plain_src: Path) -> None:
    """fallback=None must not break the pipeline or add extra frames beyond TSSE."""
    dst = tmp_path / "dst.mp3"
    _reencode_stripping(plain_src, dst)
    copy_metadata(in_path=str(plain_src), out_path=str(dst), fallback=None)

    out = ID3(dst)
    assert out["TSSE"].text == ["Podly"]
    assert "TIT2" not in out
    assert "APIC" not in out


# --------------------------- fallback_for_post --------------------------- #


def test_fallback_for_post_propagates_all_fields() -> None:
    fb = fallback_for_post(
        post_title="Ep",
        post_description="Desc",
        post_release_date=datetime.date(2026, 9, 18),
        post_image_url="https://example.com/ep.png",
        post_download_url="https://example.com/ep.mp3",
        feed_title="Show",
        feed_author="Alice",
    )
    assert fb.title == "Ep"
    assert fb.artist == "Alice"
    assert fb.album == "Show"
    assert fb.year == "2026"
    assert fb.comment == "Desc"
    assert fb.cover_url == "https://example.com/ep.png"
    assert fb.url == "https://example.com/ep.mp3"
    assert fb.genre == "Podcast"


def test_fallback_artist_falls_back_to_feed_title_when_no_author() -> None:
    fb = fallback_for_post(feed_author=None, feed_title="Show Title")
    assert fb.artist == "Show Title"


def test_fallback_cover_prefers_post_image_over_feed_image() -> None:
    fb = fallback_for_post(post_image_url="p.png", feed_image_url="f.png")
    assert fb.cover_url == "p.png"
    fb_only_feed = fallback_for_post(post_image_url=None, feed_image_url="f.png")
    assert fb_only_feed.cover_url == "f.png"
    fb_none = fallback_for_post(post_image_url=None, feed_image_url=None)
    assert fb_none.cover_url is None


def test_fallback_year_handles_datetime_datetime() -> None:
    fb = fallback_for_post(post_release_date=datetime.datetime(2026, 1, 2, 12, 30))
    assert fb.year == "2026"


def test_fallback_year_handles_date_object() -> None:
    fb = fallback_for_post(post_release_date=datetime.date(2026, 9, 18))
    assert fb.year == "2026"


def test_fallback_year_handles_iso_string() -> None:
    fb = fallback_for_post(post_release_date="2026-09-18T10:00:00Z")
    assert fb.year == "2026"


def test_fallback_year_is_none_when_release_date_missing() -> None:
    fb = fallback_for_post(post_release_date=None)
    assert fb.year is None


def test_fallback_default_genre_is_podcast() -> None:
    fb = fallback_for_post()
    assert fb.genre == "Podcast"


def test_fallback_can_override_genre() -> None:
    fb = fallback_for_post(genre="Talk Show")
    assert fb.genre == "Talk Show"
