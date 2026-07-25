#!/usr/bin/env python3
"""Real-world verification that slash-containing Audioboom GUIDs break feeds
before the fix and work after it.

Uses the live Bletchley Park Audioboom RSS feed:
https://audioboom.com/channels/451365.rss
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlparse

import feedparser
from flask import Flask

# Ensure src/ is importable when run via `uv run python ...`
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.extensions import db  # noqa: E402
from app.feeds import feed_item, get_guid  # noqa: E402
from app.guid_urls import encode_guid_for_url, post_stream_path  # noqa: E402
from app.models import Feed, Post  # noqa: E402
from app.routes.post_routes import post_bp  # noqa: E402

FEED_URL = "https://audioboom.com/channels/451365.rss"
FEED_CACHE = Path("/tmp/bletchley_audioboom.rss")


def load_live_feed() -> feedparser.FeedParserDict:
    if FEED_CACHE.exists() and FEED_CACHE.stat().st_size > 1000:
        return feedparser.parse(FEED_CACHE.read_bytes())
    return feedparser.parse(FEED_URL)


def pick_slash_guid_entry(parsed: feedparser.FeedParserDict):
    for entry in parsed.entries:
        guid = get_guid(entry)
        if "/" in guid:
            return entry, guid
    raise RuntimeError("No slash-containing GUID found in live feed")


def old_broken_enclosure_url(base: str, guid: str) -> str:
    """Pre-fix construction from feeds.py before percent-encoding."""
    return f"{base}/post/{guid}.mp3"


def demonstrate_url_breakage(guid: str) -> None:
    base = "http://localhost:5001"
    broken = old_broken_enclosure_url(base, guid)
    fixed = f"{base}{post_stream_path(guid)}"

    print("\n=== 1) Live Audioboom GUID ===")
    print(f"guid: {guid!r}")
    print(f"contains '/': {'/' in guid}")

    print("\n=== 2) Enclosure URL before fix (broken) ===")
    print(broken)
    parsed = urlparse(broken)
    print(f"path segments: {parsed.path.split('/')}")
    print(
        "problem: '/' in the GUID splits the path; Flask <string:> cannot match;"
        " podcast clients request a non-existent nested path."
    )

    print("\n=== 3) Enclosure URL after fix (encoded) ===")
    print(fixed)
    parsed_fixed = urlparse(fixed)
    print(f"path segments: {parsed_fixed.path.split('/')}")
    assert parsed_fixed.path.count("/") == 2, parsed_fixed.path  # /post/<encoded>.mp3
    assert encode_guid_for_url(guid) in parsed_fixed.path


def build_app_with_post(guid: str, audio_bytes: bytes) -> tuple[Flask, Path]:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.testing = True
    app.register_blueprint(post_bp)

    tmp = Path(tempfile.mkdtemp())
    audio_path = tmp / "processed.mp3"
    audio_path.write_bytes(audio_bytes)

    with app.app_context():
        db.init_app(app)
        db.create_all()
        feed = Feed(title="Bletchley Park", rss_url=FEED_URL)
        db.session.add(feed)
        db.session.commit()
        post = Post(
            feed_id=feed.id,
            guid=guid,
            download_url="https://example.com/audio.mp3",
            title="Live slash-GUID episode",
            whitelisted=True,
            processed_audio_path=str(audio_path),
        )
        db.session.add(post)
        db.session.commit()

    return app, audio_path


def verify_http_routing(guid: str) -> None:
    payload = b"REALWORLD-AUDIOBOOM-BYTES"
    app, _ = build_app_with_post(guid, payload)
    client = app.test_client()

    encoded = encode_guid_for_url(guid)
    fixed_path = f"/post/{encoded}.mp3"
    # Old clients/feeds would emit the raw slash GUID into the path:
    broken_path = f"/post/{guid}.mp3"

    print("\n=== 4) HTTP routing against live GUID ===")

    fixed_resp = client.get(fixed_path)
    print(f"GET {fixed_path}")
    print(f"  status={fixed_resp.status_code} body={fixed_resp.data!r}")
    assert fixed_resp.status_code == 200
    assert fixed_resp.data == payload

    json_resp = client.get(f"/post/{encoded}/json")
    print(f"GET /post/{{encoded}}/json -> {json_resp.status_code}")
    assert json_resp.status_code == 200
    assert json_resp.get_json()["guid"] == guid

    broken_resp = client.get(broken_path)
    print(f"GET {broken_path}")
    print(f"  status={broken_resp.status_code}")
    # With <path:> the unencoded request can still be routed if the server
    # keeps the slashy path intact. What matters for feeds is that generated
    # enclosure URLs are percent-encoded so clients hit a single segment.
    # Demonstrate that <string:> style matching would fail by simulating it:
    from werkzeug.routing import Map, Rule

    old_map = Map([Rule("/post/<string:p_guid>.mp3", endpoint="old")])
    new_map = Map([Rule("/post/<path:p_guid>.mp3", endpoint="new")])
    adapter_old = old_map.bind("localhost")
    adapter_new = new_map.bind("localhost")

    print("\n=== 5) Werkzeug converter comparison ===")
    try:
        endpoint, values = adapter_old.match(broken_path)
        print(f"OLD <string:> matched unexpectedly: {endpoint} {values}")
        old_matched = True
    except Exception as exc:  # noqa: BLE001
        print(f"OLD <string:> failed as expected: {type(exc).__name__}: {exc}")
        old_matched = False

    endpoint, values = adapter_new.match(broken_path)
    print(f"NEW <path:> matched unencoded path: {values['p_guid']!r}")
    assert values["p_guid"] == guid

    endpoint, values = adapter_new.match(fixed_path)
    # Matching the encoded path yields the percent-encoded segment as stored in
    # the URL before decoding depending on Werkzeug version; Flask view args are
    # decoded. For Map.match on the already-decoded path string with % escapes
    # kept, check either decoded or encoded equality.
    matched_guid = values["p_guid"]
    print(f"NEW <path:> matched encoded path as: {matched_guid!r}")
    assert matched_guid in (guid, encoded)

    assert old_matched is False, "Expected old <string:> converter to reject slash GUID"


def verify_feed_item_generation(guid: str) -> None:
    print("\n=== 6) Podly feed_item() with live GUID ===")
    post = SimpleNamespace(
        guid=guid,
        title="Live episode",
        description="desc",
        image_url=None,
        release_date=None,
        feed=None,
        duration=120,
        chapter_data=None,
        audio_len_bytes=lambda: 123,
        processed_audio_path=None,
        unprocessed_audio_path=None,
    )

    # Minimal request context for base URL resolution
    app = Flask(__name__)
    with app.test_request_context("/", base_url="http://podly.example:5001"):
        # feed_item uses flask.request; test_request_context provides it.
        from unittest import mock

        with mock.patch("app.feeds._append_feed_token_params", side_effect=lambda u: u):
            item = feed_item(post)  # type: ignore[arg-type]

    enclosure_url = item.enclosure.url
    print(f"<guid> stays verbatim: {item.guid!r}")
    print(f"enclosure url: {enclosure_url}")
    assert item.guid == guid
    assert quote(guid, safe="") in enclosure_url
    assert f"/post/{guid}.mp3" not in enclosure_url


def main() -> int:
    print(f"Fetching/parsing live feed: {FEED_URL}")
    parsed = load_live_feed()
    assert parsed.entries, "Failed to load live feed entries"
    print(f"feed title: {parsed.feed.get('title')!r}")
    print(f"entries: {len(parsed.entries)}")

    entry, guid = pick_slash_guid_entry(parsed)
    print(f"picked entry title: {entry.get('title')!r}")

    # Confirm get_guid preserves the live upstream value (the #216 behavior).
    assert get_guid(entry) == guid

    slash_count = sum(1 for e in parsed.entries if "/" in get_guid(e))
    print(f"entries with '/' in guid: {slash_count}/{len(parsed.entries)}")

    demonstrate_url_breakage(guid)
    verify_http_routing(guid)
    verify_feed_item_generation(guid)

    print("\n=== PASS: real-world Audioboom slash-GUID bug reproduced & fix verified ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
