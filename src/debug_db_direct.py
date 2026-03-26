#!/usr/bin/env python3
"""
Debug script to query database directly without starting the app.
"""

import sqlite3

DB_PATH = "/app/src/instance/sqlite3.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# First, list all tables
print("=" * 60)
print("DATABASE TABLES")
print("=" * 60)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
print(tables)
print()

print("=" * 60)
print("USER FEED SUBSCRIPTIONS")
print("=" * 60)

# Check actual table name
user_table = "users" if "users" in tables else "user"
cursor.execute(f"""
    SELECT ufs.*, u.username, f.title as feed_title
    FROM user_feed_subscription ufs
    LEFT JOIN {user_table} u ON ufs.user_id = u.id
    LEFT JOIN feed f ON ufs.feed_id = f.id
""")
for row in cursor.fetchall():
    print(f"User: {row['username']} (id={row['user_id']})")
    print(f"  Feed: {row['feed_title']} (id={row['feed_id']})")
    print(f"  auto_download_new_episodes: {row['auto_download_new_episodes']}")
    print()

print("=" * 60)
print("PENDING/RUNNING PROCESSING JOBS")
print("=" * 60)

cursor.execute("""
    SELECT pj.*, p.title as post_title
    FROM processing_job pj
    LEFT JOIN post p ON pj.post_guid = p.guid
    WHERE pj.status IN ('pending', 'running')
    ORDER BY pj.created_at DESC
""")
for row in cursor.fetchall():
    print(f"Job ID: {row['id']}")
    print(f"  Post: {row['post_title']}")
    print(f"  Status: {row['status']}")
    print(f"  Created: {row['created_at']}")
    # Check if trigger_source column exists
    try:
        print(f"  Trigger Source: {row['trigger_source']}")
    except:
        pass
    print()

print("=" * 60)
print("RECENT JOBS (last 10)")
print("=" * 60)

cursor.execute("""
    SELECT pj.*, p.title as post_title
    FROM processing_job pj
    LEFT JOIN post p ON pj.post_guid = p.guid
    ORDER BY pj.created_at DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"Job ID: {row['id']}")
    print(f"  Post: {row['post_title']}")
    print(f"  Status: {row['status']}")
    print(f"  Created: {row['created_at']}")
    try:
        print(f"  Trigger Source: {row['trigger_source']}")
    except:
        pass
    print()

conn.close()
