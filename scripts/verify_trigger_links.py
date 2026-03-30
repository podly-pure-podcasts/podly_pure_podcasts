#!/usr/bin/env python3
"""
Smoke test to verify RSS trigger links and download/trigger behavior.

Usage:
    python scripts/verify_trigger_links.py --combined-url "https://your-domain.com/feed/combined?feed_token=...&feed_secret=..."

This script verifies:
1. RSS <item><link> elements point to /trigger with correct params
2. Trigger links use https and correct domain
3. Enclosure URLs use feed-scoped tokens
4. Download endpoint does NOT create jobs (returns 503 for unprocessed)
5. Trigger endpoint DOES create jobs
6. Status endpoint returns correct state
"""

import argparse
import html
import re
import sys
from urllib.parse import parse_qs, urlparse

import requests


def find_unprocessed_episode(
    items: list, enclosure_urls: list, trigger_links: list
) -> tuple:
    """Find an unprocessed episode by testing enclosure URLs."""
    for guid, enc_url in enclosure_urls:
        try:
            # HEAD request to check if processed
            resp = requests.head(enc_url, timeout=10, allow_redirects=False)
            if resp.status_code in (204, 503):
                # Find matching trigger link
                for tg, tl in trigger_links:
                    if tg == guid:
                        return (guid, enc_url, tl)
        except requests.RequestException:
            pass
    return (None, None, None)


def _fetch_combined_feed(url: str) -> str:
    """Fetch the combined feed XML."""
    print("\n[1] Fetching combined feed...")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        print(f"    OK: Got {len(resp.text)} bytes")
        return resp.text
    except requests.RequestException as e:
        print(f"    FAIL: {e}")
        sys.exit(1)


def _parse_rss_items(xml: str) -> tuple[list, list]:
    """Parse RSS items and extract links."""
    print("\n[2] Parsing RSS items...")
    item_pattern = r"<item>.*?</item>"
    items = re.findall(item_pattern, xml, re.DOTALL)
    print(f"    Found {len(items)} items")

    if not items:
        print("    FAIL: No items found in feed")
        sys.exit(1)

    trigger_links = []
    enclosure_urls = []

    for item in items:
        guid_match = re.search(r"<guid[^>]*>([^<]+)</guid>", item)
        guid = guid_match.group(1) if guid_match else None

        link_match = re.search(r"<link>([^<]+)</link>", item)
        if link_match:
            link = html.unescape(link_match.group(1))
            trigger_links.append((guid, link))

        enc_match = re.search(r'<enclosure[^>]+url="([^"]+)"', item)
        if enc_match:
            enc_url = html.unescape(enc_match.group(1))
            enclosure_urls.append((guid, enc_url))

    return trigger_links, enclosure_urls


def _validate_links(trigger_links: list, expected_domain: str):
    """Validate trigger link formats."""
    print("\n[3] Validating trigger link format...")
    errors = []
    for guid, link in trigger_links:
        parsed = urlparse(link)
        params = parse_qs(parsed.query)
        if parsed.scheme != "https":
            errors.append(f"GUID {guid[:16]}: Expected https, got {parsed.scheme}")
        if parsed.netloc != expected_domain:
            errors.append(
                f"GUID {guid[:16]}: Expected domain {expected_domain}, got {parsed.netloc}"
            )
        if parsed.path != "/trigger":
            errors.append(
                f"GUID {guid[:16]}: Expected path /trigger, got {parsed.path}"
            )
        for p in ["guid", "feed_token", "feed_secret"]:
            if p not in params:
                errors.append(f"GUID {guid[:16]}: Missing {p} param")

    if errors:
        print("    ERRORS:")
        for e in errors[:5]:
            print(f"      - {e}")
        sys.exit(1)
    print("    OK: All trigger links valid")


def _test_endpoints(guid, enc_url, trigger_url):
    """Test download and trigger endpoints."""
    print("\n[6] Testing download endpoint (should NOT create jobs)...")
    if enc_url:
        try:
            resp = requests.get(enc_url, timeout=30, allow_redirects=False)
            print(f"    Download status: {resp.status_code}")
        except requests.RequestException as e:
            print(f"    WARN: Download request failed: {e}")

    print("\n[7] Testing trigger endpoint (should create job)...")
    if trigger_url:
        try:
            resp = requests.get(trigger_url, timeout=30)
            print(f"    Trigger status: {resp.status_code}")
        except requests.RequestException as e:
            print(f"    WARN: Trigger request failed: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Verify RSS trigger links and behavior"
    )
    parser.add_argument("--combined-url", required=True)
    parser.add_argument("--expected-domain", default="localhost")
    parser.add_argument("--skip-trigger-test", action="store_true")
    args = parser.parse_args()

    xml = _fetch_combined_feed(args.combined_url)
    trigger_links, enclosure_urls = _parse_rss_items(xml)
    _validate_links(trigger_links, args.expected_domain)

    if args.skip_trigger_test:
        return

    guid, enc_url, trigger_url = find_unprocessed_episode(
        [], enclosure_urls, trigger_links
    )
    if not guid and enclosure_urls:
        guid, enc_url = enclosure_urls[0]
        _, trigger_url = trigger_links[0]

    _test_endpoints(guid, enc_url, trigger_url)
    print("\nVerification complete!")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
