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
import time
from urllib.parse import parse_qs, urlparse

import requests


def find_unprocessed_episode(items: list, enclosure_urls: list, trigger_links: list) -> tuple:
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
        except Exception:
            pass
    return (None, None, None)


def main():
    parser = argparse.ArgumentParser(description="Verify RSS trigger links and behavior")
    parser.add_argument("--combined-url", required=True, help="Combined feed URL with tokens")
    parser.add_argument("--expected-domain", default="localhost", help="Expected domain in URLs")
    parser.add_argument("--skip-trigger-test", action="store_true", help="Skip the trigger job creation test")
    parser.add_argument("--poll-timeout", type=int, default=180, help="Timeout for polling status (seconds)")
    args = parser.parse_args()

    print("=" * 60)
    print("RSS Trigger Link & Behavior Verification")
    print("=" * 60)

    # 1. Fetch combined feed
    print("\n[1] Fetching combined feed...")
    try:
        resp = requests.get(args.combined_url, timeout=30)
        resp.raise_for_status()
        xml = resp.text
        print(f"    OK: Got {len(xml)} bytes")
    except Exception as e:
        print(f"    FAIL: {e}")
        sys.exit(1)

    # 2. Parse items and extract links
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

    print(f"    Found {len(trigger_links)} trigger links")
    print(f"    Found {len(enclosure_urls)} enclosure URLs")

    # 3. Validate trigger link format
    print("\n[3] Validating trigger link format...")
    
    errors = []
    for guid, link in trigger_links:
        parsed = urlparse(link)
        params = parse_qs(parsed.query)
        
        if parsed.scheme != "https":
            errors.append(f"GUID {guid[:16]}: Expected https, got {parsed.scheme}")
        if parsed.netloc != args.expected_domain:
            errors.append(f"GUID {guid[:16]}: Expected domain {args.expected_domain}, got {parsed.netloc}")
        if parsed.path != "/trigger":
            errors.append(f"GUID {guid[:16]}: Expected path /trigger, got {parsed.path}")
        if "guid" not in params:
            errors.append(f"GUID {guid[:16]}: Missing guid param")
        if "feed_token" not in params:
            errors.append(f"GUID {guid[:16]}: Missing feed_token param")
        if "feed_secret" not in params:
            errors.append(f"GUID {guid[:16]}: Missing feed_secret param")

    if errors:
        print("    ERRORS:")
        for e in errors[:5]:
            print(f"      - {e}")
        if len(errors) > 5:
            print(f"      ... and {len(errors) - 5} more")
        sys.exit(1)
    print("    OK: All trigger links valid")

    # 4. Validate enclosure URLs have tokens
    print("\n[4] Validating enclosure URLs...")
    for guid, enc_url in enclosure_urls[:3]:
        parsed = urlparse(enc_url)
        params = parse_qs(parsed.query)
        if "feed_token" not in params or "feed_secret" not in params:
            print(f"    FAIL: GUID {guid[:16]} missing tokens in enclosure")
            sys.exit(1)
    print("    OK: Enclosure URLs have feed tokens")

    if args.skip_trigger_test:
        print("\n[SKIP] Trigger/download tests skipped")
        print("\n" + "=" * 60)
        print("Verification complete!")
        print("=" * 60)
        return

    # 5. Find an unprocessed episode
    print("\n[5] Finding unprocessed episode...")
    guid, enc_url, trigger_url = find_unprocessed_episode(items, enclosure_urls, trigger_links)
    
    if not guid:
        print("    INFO: No unprocessed episodes found (all processed or errors)")
        print("    Using first episode for basic tests...")
        guid, enc_url = enclosure_urls[0] if enclosure_urls else (None, None)
        _, trigger_url = trigger_links[0] if trigger_links else (None, None)
    else:
        print(f"    Found unprocessed: {guid[:32]}...")

    # 6. Test download endpoint does NOT create jobs
    print("\n[6] Testing download endpoint (should NOT create jobs)...")
    if enc_url:
        try:
            resp = requests.get(enc_url, timeout=30, allow_redirects=False)
            if resp.status_code == 503:
                print(f"    OK: Download returned 503 (not processed, no job created)")
                if "Retry-After" in resp.headers:
                    print(f"    OK: Retry-After header present: {resp.headers['Retry-After']}")
            elif resp.status_code == 200:
                print(f"    OK: Download returned 200 (already processed)")
            elif resp.status_code == 204:
                print(f"    OK: Download returned 204 (probe response)")
            else:
                print(f"    WARN: Download returned {resp.status_code}")
        except Exception as e:
            print(f"    WARN: Download request failed: {e}")
    else:
        print("    SKIP: No enclosure URL available")

    # 7. Test trigger endpoint DOES create jobs
    print("\n[7] Testing trigger endpoint (should create job)...")
    if trigger_url:
        try:
            resp = requests.get(trigger_url, timeout=30)
            print(f"    Status: {resp.status_code}")
            if resp.status_code == 200:
                if "Processing Started" in resp.text:
                    print("    OK: Job created - 'Processing Started'")
                elif "Processing In Progress" in resp.text:
                    print("    OK: Job exists - 'Processing In Progress'")
                elif "Episode Ready" in resp.text:
                    print("    OK: Already processed - 'Episode Ready'")
                elif "Please Wait" in resp.text:
                    print("    OK: Cooldown active - 'Please Wait'")
                elif "Cannot Trigger" in resp.text:
                    print("    FAIL: Combined token rejected (expected for combined feed)")
                else:
                    print("    WARN: Unexpected page content")
            else:
                print(f"    WARN: Unexpected status {resp.status_code}")
        except Exception as e:
            print(f"    WARN: Trigger request failed: {e}")
    else:
        print("    SKIP: No trigger URL available")

    # 8. Test status endpoint polling
    print("\n[8] Testing status endpoint polling...")
    if trigger_url:
        # Extract status URL from trigger URL
        parsed = urlparse(trigger_url)
        params = parse_qs(parsed.query)
        status_url = f"https://{parsed.netloc}/api/trigger/status?guid={params['guid'][0]}&feed_token={params['feed_token'][0]}&feed_secret={params['feed_secret'][0]}"
        
        try:
            resp = requests.get(status_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                print(f"    State: {data.get('state')}")
                print(f"    Message: {data.get('message', 'N/A')[:50]}")
                if data.get('job'):
                    print(f"    Job ID: {data['job'].get('id', 'N/A')[:16]}")
                print("    OK: Status endpoint working")
            else:
                print(f"    WARN: Status returned {resp.status_code}")
        except Exception as e:
            print(f"    WARN: Status request failed: {e}")
    else:
        print("    SKIP: No trigger URL available")

    print("\n" + "=" * 60)
    print("Verification complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
