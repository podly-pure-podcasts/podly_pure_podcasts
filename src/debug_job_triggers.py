#!/usr/bin/env python3
"""
Debug script to trace what triggers job processing.
Run this inside the Docker container to explore the issue.
"""

import sys
sys.path.insert(0, '/app/src')

from app import create_app
from app.extensions import db
from app.models import Feed, Post, User, UserFeedSubscription, ProcessingJob

app = create_app()

with app.app_context():
    # Check all subscriptions and their auto_download status
    print("=" * 60)
    print("USER FEED SUBSCRIPTIONS")
    print("=" * 60)
    
    subscriptions = UserFeedSubscription.query.all()
    for sub in subscriptions:
        user = User.query.get(sub.user_id)
        feed = Feed.query.get(sub.feed_id)
        print(f"User: {user.username if user else 'N/A'} (id={sub.user_id})")
        print(f"  Feed: {feed.title if feed else 'N/A'} (id={sub.feed_id})")
        print(f"  auto_download_new_episodes: {sub.auto_download_new_episodes}")
        print()
    
    # Check pending jobs
    print("=" * 60)
    print("PENDING PROCESSING JOBS")
    print("=" * 60)
    
    pending_jobs = ProcessingJob.query.filter_by(status="pending").all()
    for job in pending_jobs:
        post = Post.query.filter_by(guid=job.post_guid).first()
        print(f"Job ID: {job.id}")
        print(f"  Post GUID: {job.post_guid}")
        print(f"  Post Title: {post.title if post else 'N/A'}")
        print(f"  Status: {job.status}")
        print(f"  Created: {job.created_at}")
        print(f"  Trigger Source: {getattr(job, 'trigger_source', 'N/A')}")
        print()
    
    # Check running jobs
    print("=" * 60)
    print("RUNNING PROCESSING JOBS")
    print("=" * 60)
    
    running_jobs = ProcessingJob.query.filter_by(status="running").all()
    for job in running_jobs:
        post = Post.query.filter_by(guid=job.post_guid).first()
        print(f"Job ID: {job.id}")
        print(f"  Post GUID: {job.post_guid}")
        print(f"  Post Title: {post.title if post else 'N/A'}")
        print(f"  Status: {job.status}")
        print(f"  Created: {job.created_at}")
        print(f"  Trigger Source: {getattr(job, 'trigger_source', 'N/A')}")
        print()
    
    # Check recent jobs (last 10)
    print("=" * 60)
    print("RECENT JOBS (last 10)")
    print("=" * 60)
    
    recent_jobs = ProcessingJob.query.order_by(ProcessingJob.created_at.desc()).limit(10).all()
    for job in recent_jobs:
        post = Post.query.filter_by(guid=job.post_guid).first()
        print(f"Job ID: {job.id}")
        print(f"  Post: {post.title if post else 'N/A'}")
        print(f"  Status: {job.status}")
        print(f"  Created: {job.created_at}")
        print(f"  Trigger Source: {getattr(job, 'trigger_source', 'N/A')}")
        print()
