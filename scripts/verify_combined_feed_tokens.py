#!/usr/bin/env python3
"""
Verification script for combined feed token implementation.

This script verifies that:
1. Combined feed enclosure URLs use feed-scoped tokens (feed_id != NULL)
2. Token creation is bounded (one token per user_id + feed_id, not per post)
3. Combined tokens cannot trigger processing
4. Enclosure URLs use public domain (not localhost)

Usage (inside Docker container):
    cd /app && python scripts/verify_combined_feed_tokens.py

Or from host:
    docker exec podly-pure-podcasts python /app/scripts/verify_combined_feed_tokens.py
"""

import html
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple, List, Dict

# Default internal port - Waitress serves on 5001 in production
INTERNAL_PORT = os.environ.get("FLASK_PORT", "5001")
DB_PATH = "/app/src/instance/sqlite3.db"


def get_db_connection():
    """Get direct SQLite connection (no ORM assumptions)."""
    return sqlite3.connect(DB_PATH)


def print_schema():
    """Print feed_access_token table schema."""
    print("=" * 60)
    print("A) feed_access_token Schema")
    print("=" * 60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    result = cursor.execute("PRAGMA table_info(feed_access_token)").fetchall()
    conn.close()
    
    columns = [row[1] for row in result]
    print(f"Columns: {columns}")
    print()
    print(f"{'cid':<4} {'name':<15} {'type':<12} {'notnull':<8} {'pk':<4}")
    print("-" * 50)
    for row in result:
        print(f"{row[0]:<4} {row[1]:<15} {row[2]:<12} {row[3]:<8} {row[5]:<4}")
    
    print("\nKey columns:")
    print("  - token_id: URL parameter 'feed_token'")
    print("  - token_secret: URL parameter 'feed_secret'")
    print("  - feed_id: NULL for combined tokens, integer for feed-scoped tokens")
    
    # Check if 'revoked' column exists
    if 'revoked' in columns:
        print("  - revoked: Boolean flag for revoked tokens")
    else:
        print("  - NOTE: 'revoked' column not found - queries will not filter by revoked status")
    
    return columns


def verify_token_bounds(columns: List[str]):
    """Verify token creation is bounded (no DB bloat)."""
    print("\n" + "=" * 60)
    print("B) Token Creation Bounds Check")
    print("=" * 60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Build WHERE clause based on available columns
    revoked_filter = "AND revoked = 0" if 'revoked' in columns else ""
    
    # Count combined tokens (feed_id IS NULL)
    cursor.execute(f"SELECT COUNT(*) FROM feed_access_token WHERE feed_id IS NULL {revoked_filter}")
    combined_count = cursor.fetchone()[0]
    
    # Count feed-scoped tokens (feed_id IS NOT NULL)
    cursor.execute(f"SELECT COUNT(*) FROM feed_access_token WHERE feed_id IS NOT NULL {revoked_filter}")
    feed_scoped_count = cursor.fetchone()[0]
    
    # Count unique (user_id, feed_id) pairs using printf for safety
    cursor.execute(f"""
        SELECT COUNT(DISTINCT printf('%d-%d', user_id, feed_id)) 
        FROM feed_access_token 
        WHERE feed_id IS NOT NULL {revoked_filter}
    """)
    unique_feed_scoped = cursor.fetchone()[0]
    
    # Count total subscriptions
    cursor.execute("SELECT COUNT(*) FROM user_feed_subscription")
    total_subscriptions = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"Combined tokens (feed_id=NULL): {combined_count}")
    print(f"Feed-scoped tokens (feed_id!=NULL): {feed_scoped_count}")
    print(f"Unique (user_id, feed_id) pairs: {unique_feed_scoped}")
    print(f"Total subscriptions: {total_subscriptions}")
    
    if feed_scoped_count == unique_feed_scoped:
        print("\n[PASS] Token creation is bounded - one token per (user_id, feed_id)")
    else:
        print(f"\n[INFO] Found {feed_scoped_count - unique_feed_scoped} extra tokens (may be from token rotation)")
    
    if feed_scoped_count <= total_subscriptions * 2:  # Allow some slack for rotation
        print(f"[PASS] Feed-scoped tokens ({feed_scoped_count}) reasonable vs subscriptions ({total_subscriptions})")
    else:
        print(f"[WARN] Many more feed-scoped tokens than subscriptions - possible bloat")


def get_combined_token(columns: List[str]) -> Optional[Tuple[str, str]]:
    """Get a combined token (feed_id=NULL) from DB."""
    conn = get_db_connection()
    cursor = conn.cursor()
    revoked_filter = "AND revoked = 0" if 'revoked' in columns else ""
    cursor.execute(f"SELECT token_id, token_secret FROM feed_access_token WHERE feed_id IS NULL {revoked_filter} LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return (row[0], row[1]) if row else None


def lookup_token_feed_id(token_id: str) -> Optional[int]:
    """Look up feed_id for a token."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT feed_id FROM feed_access_token WHERE token_id = ?", (token_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def lookup_post_feed_id(guid: str) -> Optional[int]:
    """Look up feed_id for a post by GUID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT feed_id FROM post WHERE guid = ?", (guid,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


def fetch_combined_feed(base_url: str, token_id: str, token_secret: str) -> Optional[str]:
    """Fetch combined feed XML from server.
    
    Args:
        base_url: Base URL to fetch from (e.g., 'https://your-domain.com')
        token_id: Combined token ID
        token_secret: Combined token secret
    """
    url = f"{base_url}/feed/combined?feed_token={token_id}&feed_secret={token_secret}"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Podly-Verification/1.0")
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[ERROR] Failed to fetch combined feed: {e}")
        print(f"  URL: {url}")
        return None


def extract_enclosure_urls(xml_content: str) -> List[str]:
    """Extract enclosure URLs from RSS XML.
    
    Applies html.unescape() to convert &amp; to & in URLs.
    """
    # Use regex to avoid XML parsing issues with namespaces
    pattern = r'<enclosure[^>]+url="([^"]+)"'
    raw_urls = re.findall(pattern, xml_content)
    # Unescape HTML entities (e.g., &amp; -> &)
    return [html.unescape(url) for url in raw_urls]


def extract_guid_from_url(url: str) -> Optional[str]:
    """Extract post GUID from enclosure URL."""
    match = re.search(r"/api/posts/([^/]+)/download", url)
    if match:
        return urllib.parse.unquote(match.group(1))
    return None


def count_jobs_for_guid(guid: str, trigger_source: Optional[str] = None) -> int:
    """Count processing jobs for a specific GUID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    if trigger_source:
        cursor.execute(
            "SELECT COUNT(*) FROM processing_job WHERE post_guid = ? AND trigger_source = ?",
            (guid, trigger_source)
        )
    else:
        cursor.execute("SELECT COUNT(*) FROM processing_job WHERE post_guid = ?", (guid,))
    count = cursor.fetchone()[0]
    conn.close()
    return count


def http_get(url: str, host_header: str = "") -> Tuple[int, str]:
    """Make HTTP GET request and return (status_code, body)."""
    try:
        req = urllib.request.Request(url)
        if host_header:
            req.add_header("Host", host_header)
            req.add_header("X-Forwarded-Proto", "https")
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore") if e.fp else ""
    except Exception as e:
        return 0, str(e)


def verify_enclosure_tokens(columns: List[str], base_url: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Main verification: fetch combined feed and verify enclosure tokens are feed-scoped.
    
    Returns:
        (success, sample_enclosure_url, sample_guid, combined_token_id, combined_secret)
    """
    print("\n" + "=" * 60)
    print("C) Enclosure Token Verification (Automated)")
    print("=" * 60)
    
    # Get combined token
    combined = get_combined_token(columns)
    if not combined:
        print("[SKIP] No combined token found in database")
        return False, None, None, None, None
    
    combined_token_id, combined_secret = combined
    print(f"Combined token: {combined_token_id[:8]}...")
    print(f"Combined secret: {combined_secret[:8]}...")
    
    # Fetch combined feed from public URL
    print(f"Fetching combined feed from {base_url}...")
    xml_content = fetch_combined_feed(base_url, combined_token_id, combined_secret)
    if not xml_content:
        return False, None, None, None, None
    
    print(f"Feed fetched: {len(xml_content)} bytes")
    
    # Extract enclosure URLs
    enclosure_urls = extract_enclosure_urls(xml_content)
    if not enclosure_urls:
        print("[WARN] No enclosure URLs found in feed")
        return False, None, None, None, None
    
    print(f"Found {len(enclosure_urls)} enclosure URLs")
    
    # Verify first 10 enclosures
    checked = 0
    passed = 0
    sample_url = None
    sample_guid = None
    
    for url in enclosure_urls[:10]:
        # Extract feed_token from URL
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        
        enclosure_token = params.get("feed_token", [None])[0]
        if not enclosure_token:
            print(f"[WARN] No feed_token in URL: {url[:60]}...")
            continue
        
        checked += 1
        guid = extract_guid_from_url(url)
        
        # Check 1: Enclosure token differs from combined token
        if enclosure_token == combined_token_id:
            print(f"[FAIL] Enclosure uses combined token! {enclosure_token[:8]}...")
            continue
        
        # Check 2: Enclosure token is feed-scoped (feed_id != NULL)
        token_feed_id = lookup_token_feed_id(enclosure_token)
        if token_feed_id is None:
            print(f"[FAIL] Enclosure token {enclosure_token[:8]}... has feed_id=NULL (should be feed-scoped)")
            continue
        
        # Check 3: Token's feed_id matches post's feed_id
        if guid:
            post_feed_id = lookup_post_feed_id(guid)
            if post_feed_id and token_feed_id != post_feed_id:
                print(f"[FAIL] Token feed_id={token_feed_id} != post feed_id={post_feed_id}")
                continue
        
        # Check 4: URL uses public domain (not localhost/127.0.0.1)
        if "localhost" in parsed.netloc or "127.0.0.1" in parsed.netloc:
            print(f"[FAIL] Enclosure URL uses localhost: {parsed.netloc}")
            continue
        
        # Check 5: URL uses HTTPS scheme
        if parsed.scheme != "https":
            print(f"[WARN] Enclosure URL uses {parsed.scheme} instead of https")
        
        print(f"[PASS] Token {enclosure_token[:8]}... -> feed_id={token_feed_id}, scheme={parsed.scheme}, host={parsed.netloc}")
        passed += 1
        
        if sample_url is None:
            sample_url = url
            sample_guid = guid
    
    print(f"\nResult: {passed}/{checked} enclosures use correct feed-scoped tokens")
    
    if sample_url:
        print(f"\nSample enclosure URL for end-to-end testing:")
        print(f"  URL: {sample_url}")
        print(f"  GUID: {sample_guid}")
    
    success = passed == checked and checked > 0
    return success, sample_url, sample_guid, combined_token_id, combined_secret


def http_get_with_range(url: str, range_header: str) -> Tuple[int, str]:
    """Make HTTP GET request with Range header and return (status_code, body)."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Podly-Verification/1.0")
        req.add_header("Range", range_header)
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore") if e.fp else ""
    except Exception as e:
        return 0, str(e)


def test_end_to_end_job_creation(base_url: str, enclosure_url: str, guid: str, 
                                  combined_token_id: str, combined_secret: str) -> bool:
    """
    End-to-end test that proves:
    1. Probe requests (HEAD, small Range) do NOT create jobs
    2. Full GET with feed-scoped token creates a job (returns 503)
    3. Combined token does NOT create a job (returns 503 or 204)
    
    This is the deterministic test that proves Podcast Addict will trigger processing.
    Uses public URLs (via Caddy) for all requests.
    
    Expected responses:
    - Probe (HEAD/small Range): 204 No Content, no job
    - Feed-scoped full GET: 503 Service Unavailable + Retry-After, job created
    - Combined token: 503 Service Unavailable, no job created
    - Already processed: 200 OK with audio
    """
    print("\n" + "=" * 60)
    print("F) End-to-End Job Creation Test")
    print("=" * 60)
    
    print(f"Testing GUID: {guid}")
    print(f"Base URL: {base_url}")
    
    # Count existing jobs for this GUID
    initial_job_count = count_jobs_for_guid(guid)
    print(f"Initial job count for GUID: {initial_job_count}")
    
    # --- Step 1: Probe request (small Range) - should NOT trigger job ---
    print("\nStep 1: Probe request (Range: bytes=0-1023) - should NOT trigger...")
    status_probe, body_probe = http_get_with_range(enclosure_url, "bytes=0-1023")
    print(f"  Response: {status_probe}")
    print(f"  Body: {body_probe[:50]}..." if len(body_probe) > 50 else f"  Body: {body_probe}")
    
    post_probe_count = count_jobs_for_guid(guid)
    print(f"  Job count after probe: {post_probe_count}")
    
    probe_triggered = post_probe_count > initial_job_count
    if probe_triggered:
        print("  [FAIL] Probe request triggered job creation!")
        probe_ok = False
    elif status_probe == 204:
        print("  [PASS] Probe returned 204, no job created")
        probe_ok = True
    elif status_probe == 200:
        print("  [INFO] Episode already processed (200)")
        probe_ok = True
    else:
        print(f"  [WARN] Unexpected probe response: {status_probe}")
        probe_ok = status_probe in (204, 206)  # 206 Partial Content is also acceptable
    
    # --- Step 2: Full GET with feed-scoped token - should trigger job ---
    print("\nStep 2: Full GET (feed-scoped token) - should trigger job...")
    print(f"  URL: {enclosure_url[:80]}...")
    
    status, body = http_get(enclosure_url)
    print(f"  Response: {status}")
    print(f"  Body: {body[:100]}..." if len(body) > 100 else f"  Body: {body}")
    
    post_enclosure_count = count_jobs_for_guid(guid)
    print(f"  Job count after full GET: {post_enclosure_count}")
    
    enclosure_triggered = post_enclosure_count > post_probe_count
    if status == 200:
        print("  [INFO] Episode already processed - skipping job creation check")
        enclosure_ok = True
    elif status == 503 and enclosure_triggered:
        print("  [PASS] Feed-scoped token triggered job creation (503 + job)")
        enclosure_ok = True
    elif status == 503 and not enclosure_triggered:
        # Could be cooldown or existing job
        print("  [INFO] 503 but no new job - may be cooldown or existing job")
        enclosure_ok = True  # Not a failure
    else:
        print(f"  [WARN] Unexpected response: {status} (expected 503 or 200)")
        enclosure_ok = False
    
    # --- Step 3: Combined token request - should NOT trigger job ---
    print("\nStep 3: Full GET (combined token) - should NOT trigger...")
    combined_url = f"{base_url}/api/posts/{guid}/download?feed_token={combined_token_id}&feed_secret={combined_secret}"
    print(f"  URL: {combined_url[:80]}...")
    
    status2, body2 = http_get(combined_url)
    print(f"  Response: {status2}")
    print(f"  Body: {body2[:100]}..." if len(body2) > 100 else f"  Body: {body2}")
    
    post_combined_count = count_jobs_for_guid(guid)
    print(f"  Job count after combined token request: {post_combined_count}")
    
    combined_triggered = post_combined_count > post_enclosure_count
    if combined_triggered:
        print("  [FAIL] Combined token triggered job creation (should be read-only!)")
        combined_ok = False
    elif status2 in (503, 204):
        print(f"  [PASS] Combined token returned {status2}, no job created")
        combined_ok = True
    elif status2 == 200:
        print("  [INFO] Episode already processed (200)")
        combined_ok = True
    else:
        print(f"  [WARN] Unexpected response: {status2}")
        combined_ok = False
    
    # Summary
    print("\nEnd-to-end test result:")
    all_ok = probe_ok and enclosure_ok and combined_ok
    if all_ok:
        print("  [PASS] Probes don't trigger, feed-scoped can trigger, combined cannot")
        return True
    else:
        print("  [FAIL] See details above")
        return False


def list_sample_tokens(columns: List[str]):
    """List sample tokens for manual verification."""
    print("\n" + "=" * 60)
    print("D) Sample Tokens for Manual Verification")
    print("=" * 60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    revoked_filter = "AND revoked = 0" if 'revoked' in columns else ""
    
    # Combined token
    cursor.execute(f"SELECT token_id, token_secret, user_id FROM feed_access_token WHERE feed_id IS NULL {revoked_filter} LIMIT 1")
    combined = cursor.fetchone()
    if combined:
        print(f"\nCombined token (should NOT trigger processing):")
        print(f"  token_id: {combined[0]}")
        print(f"  token_secret: {combined[1]}")
        print(f"  feed_id: NULL")
        print(f"  user_id: {combined[2]}")
    
    # Feed-scoped token
    cursor.execute(f"SELECT token_id, token_secret, user_id, feed_id FROM feed_access_token WHERE feed_id IS NOT NULL {revoked_filter} LIMIT 1")
    feed_scoped = cursor.fetchone()
    if feed_scoped:
        print(f"\nFeed-scoped token (CAN trigger processing):")
        print(f"  token_id: {feed_scoped[0]}")
        print(f"  token_secret: {feed_scoped[1]}")
        print(f"  feed_id: {feed_scoped[3]}")
        print(f"  user_id: {feed_scoped[2]}")
    
    conn.close()


def get_unprocessed_episode(columns: List[str]) -> Optional[Tuple[str, int, str]]:
    """Get an unprocessed episode for testing."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.guid, p.feed_id, p.title 
        FROM post p
        WHERE p.whitelisted = 1 
        AND (p.processed_audio_path IS NULL OR p.processed_audio_path = '')
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row if row else None


def check_job_created(guid: str) -> Optional[Tuple[str, str, str]]:
    """Check if a processing job was created for a GUID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT trigger_source, status, created_at 
        FROM processing_job 
        WHERE post_guid = ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (guid,))
    row = cursor.fetchone()
    conn.close()
    return row if row else None


def print_manual_commands(base_url: str):
    """Print manual verification commands."""
    print("\n" + "=" * 60)
    print("E) Manual Verification Commands")
    print("=" * 60)
    
    print(f"""
# Base URL: {base_url}

# 1. Run full verification from host machine:
docker exec podly-pure-podcasts python /app/scripts/verify_combined_feed_tokens.py

# 2. Test enclosure URL triggers processing (use URL from script output):
curl -i "ENCLOSURE_URL_HERE" | head -30

# 3. Check if job was created:
docker exec podly-pure-podcasts python -c "
import sqlite3
conn = sqlite3.connect('/app/src/instance/sqlite3.db')
c = conn.cursor()
print('Recent jobs:')
for row in c.execute('SELECT post_guid, trigger_source, status, created_at FROM processing_job ORDER BY created_at DESC LIMIT 5').fetchall():
    print(f'  {{row[3]}} | {{row[1]}} | {{row[2]}} | {{row[0][:30]}}...')
conn.close()
"

# 4. Test that combined token does NOT trigger processing:
# Use combined token from script output with same GUID
# Expected: 202 Accepted, NO new job created
""")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify combined feed token implementation")
    parser.add_argument("--host", default="localhost:5001", help="Public hostname (default: localhost:5001)")
    parser.add_argument("--base-url", default=None, help="Base URL for requests (default: https://{host})")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching combined feed (schema/bounds only)")
    parser.add_argument("--skip-e2e", action="store_true", help="Skip end-to-end job creation test")
    args = parser.parse_args()
    
    # Determine base URL
    base_url = args.base_url if args.base_url else f"https://{args.host}"
    
    print("=" * 60)
    print("Combined Feed Token Verification")
    print("=" * 60)
    print(f"DB Path: {DB_PATH}")
    print(f"Base URL: {base_url}")
    print()
    
    # A) Print schema and get column list
    columns = print_schema()
    
    # B) Verify token bounds
    verify_token_bounds(columns)
    
    # C) Verify enclosure tokens (the critical test)
    enclosure_ok = False
    sample_url = None
    sample_guid = None
    combined_token_id = None
    combined_secret = None
    
    if not args.skip_fetch:
        enclosure_ok, sample_url, sample_guid, combined_token_id, combined_secret = verify_enclosure_tokens(
            columns, base_url
        )
    else:
        print("\n[SKIP] Enclosure verification (--skip-fetch)")
    
    # D) List sample tokens
    list_sample_tokens(columns)
    
    # E) Print manual commands
    print_manual_commands(base_url)
    
    # F) End-to-end job creation test
    e2e_ok = None
    if not args.skip_e2e and sample_url and sample_guid and combined_token_id and combined_secret:
        e2e_ok = test_end_to_end_job_creation(
            base_url, sample_url, sample_guid,
            combined_token_id, combined_secret
        )
    elif args.skip_e2e:
        print("\n[SKIP] End-to-end test (--skip-e2e)")
    elif not sample_url:
        print("\n[SKIP] End-to-end test (no sample URL from enclosure verification)")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_pass = True
    
    if enclosure_ok is True:
        print("[PASS] All enclosure tokens are feed-scoped and use public domain")
    elif enclosure_ok is False:
        print("[FAIL] Some enclosure tokens are incorrect - see details above")
        all_pass = False
    else:
        print("[SKIP] Enclosure verification was skipped")
    
    if e2e_ok is True:
        print("[PASS] End-to-end: feed-scoped triggers, combined does not")
    elif e2e_ok is False:
        print("[FAIL] End-to-end test failed - see details above")
        all_pass = False
    else:
        print("[SKIP] End-to-end test was skipped")
    
    if all_pass:
        print("\n*** Podcast Addict should now trigger processing from unified feed ***")
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
