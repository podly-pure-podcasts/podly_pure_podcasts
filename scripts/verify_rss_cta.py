#!/usr/bin/env python3
"""
Verify that RSS feeds include the processing CTA in description and content:encoded.
This script fetches a feed and checks that a known GUID has:
1. <link> pointing to /trigger?...
2. CTA text in <description>
3. CTA text in <content:encoded>

Usage:
    python scripts/verify_rss_cta.py <feed_url> [guid]
    
Example:
    python scripts/verify_rss_cta.py "https://your-domain.com/feed/1?feed_token=xxx&feed_secret=yyy"
"""

import sys
import xml.etree.ElementTree as ET
import urllib.request
import ssl

def verify_rss_cta(feed_url: str, target_guid: str | None = None) -> bool:
    """Verify RSS feed has CTA in description and content:encoded."""
    
    # Fetch the feed
    print(f"Fetching: {feed_url[:80]}...")
    
    # Create SSL context that doesn't verify (for self-signed certs in dev)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        with urllib.request.urlopen(feed_url, context=ctx, timeout=30) as response:
            xml_content = response.read().decode('utf-8')
    except Exception as e:
        print(f"ERROR: Failed to fetch feed: {e}")
        return False
    
    # Parse XML
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"ERROR: Failed to parse XML: {e}")
        return False
    
    # Define namespaces
    namespaces = {
        'content': 'http://purl.org/rss/1.0/modules/content/',
        'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd',
    }
    
    # Find all items
    items = root.findall('.//item')
    print(f"Found {len(items)} items in feed")
    
    if not items:
        print("ERROR: No items found in feed")
        return False
    
    # Check first item or target GUID
    checked = 0
    passed = 0
    
    for item in items:
        guid_elem = item.find('guid')
        guid = guid_elem.text if guid_elem is not None else None
        
        if target_guid and guid != target_guid:
            continue
        
        title_elem = item.find('title')
        title = title_elem.text if title_elem is not None else "Unknown"
        
        print(f"\n--- Checking: {title[:60]}... ---")
        print(f"    GUID: {guid}")
        
        checked += 1
        item_passed = True
        
        # Check <link>
        link_elem = item.find('link')
        link = link_elem.text if link_elem is not None else ""
        if '/trigger?' in link:
            print(f"    [OK] <link> points to trigger: {link[:80]}...")
        else:
            print(f"    [FAIL] <link> does not point to trigger: {link[:80]}...")
            item_passed = False
        
        # Check <description>
        desc_elem = item.find('description')
        desc = desc_elem.text if desc_elem is not None else ""
        if 'Process this episode' in desc or 'queue ad removal' in desc.lower():
            print(f"    [OK] <description> contains CTA ({len(desc)} chars)")
        else:
            print(f"    [FAIL] <description> missing CTA ({len(desc)} chars)")
            item_passed = False
        
        # Check <content:encoded>
        content_elem = item.find('content:encoded', namespaces)
        content = content_elem.text if content_elem is not None else ""
        if 'Process this episode' in content or 'queue ad removal' in content.lower():
            print(f"    [OK] <content:encoded> contains CTA ({len(content)} chars)")
        else:
            print(f"    [FAIL] <content:encoded> missing CTA ({len(content)} chars)")
            item_passed = False
        
        if item_passed:
            passed += 1
        
        # Only check first 3 items unless specific GUID requested
        if not target_guid and checked >= 3:
            break
    
    print(f"\n=== Summary: {passed}/{checked} items passed ===")
    return passed == checked


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    feed_url = sys.argv[1]
    target_guid = sys.argv[2] if len(sys.argv) > 2 else None
    
    success = verify_rss_cta(feed_url, target_guid)
    sys.exit(0 if success else 1)
