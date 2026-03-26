# On-Demand Processing: Problem & Solution

**Last Updated:** January 2026

## The Problem

We wanted podcast apps (Overcast, Pocket Casts, Apple Podcasts) to trigger episode processing when users download unprocessed episodes. The app would retry until the episode was ready.

### Why It Was Hard

1. **Podcast apps don't send cookies** - No session auth available
2. **Apps probe before downloading** - HEAD requests and small Range requests
3. **Combined feeds aggregate all episodes** - Polling could trigger mass processing
4. **Apps cache failures** - 404 = permanent failure, no retry

### What We Tried (And Failed)

| Approach | Why It Failed |
|----------|---------------|
| Trigger on any GET request | RSS feed polling triggered processing for ALL episodes |
| Block Range requests as "probes" | Real downloads use Range requests (Overcast, Pocket Casts) |
| Use combined feed token for enclosures | Any RSS poll could trigger processing |
| Return 404 for unprocessed | Apps treat 404 as permanent, never retry |

---

## The Solution

### 1. Separate Trigger Page from Download Endpoint

Instead of triggering processing from the download endpoint, we use a **dedicated trigger page**:

```
RSS <item><link> --> /trigger?guid=X&feed_token=Y&feed_secret=Z
RSS <enclosure>  --> /api/posts/X/download?feed_token=Y&feed_secret=Z
```

- **Trigger page**: User clicks link in podcast app's show notes, sees progress, waits for completion
- **Download endpoint**: Only serves audio (processed or original), never triggers processing

### 2. Feed-Scoped Tokens

Combined feeds use two token types:

| Token | `feed_id` | Can Trigger? | Used For |
|-------|-----------|--------------|----------|
| Combined | `NULL` | No | Feed URL |
| Feed-scoped | `<int>` | Yes | Enclosure URLs |

Each episode's enclosure URL contains a **feed-scoped token** (not the combined token), preventing mass triggering.

### 3. Trigger Page Flow

```
User taps "Process this episode" link in podcast app
    |
    v
/trigger?guid=X&feed_token=Y&feed_secret=Z
    |
    +--> Validates token (feed-scoped, not combined)
    +--> Checks if already processed --> redirect to download
    +--> Checks for existing job --> show progress
    +--> Creates job, shows progress page with auto-refresh
    |
    v
User waits, page auto-refreshes until complete
    |
    v
Redirect to download URL
```

### 4. Download Endpoint Behavior

```python
GET /api/posts/{guid}/download
    |
    +--> Processed? --> 200 + audio file
    +--> Not processed? --> 302 redirect to original audio URL
```

No 202, no Retry-After, no triggering. Just serve what's available.

---

## Key Files

| File | Purpose |
|------|---------|
| `src/app/routes/post_routes.py` | `/trigger` endpoint, `/api/posts/<guid>/download` |
| `src/app/feeds.py` | RSS generation with feed-scoped tokens |
| `src/app/auth/feed_tokens.py` | Token creation/validation |

---

## Why This Works

1. **No accidental triggers** - Processing only starts when user explicitly clicks trigger link
2. **No mass processing** - Feed polling never triggers anything
3. **Works with all apps** - Trigger page is just a web page, works everywhere
4. **Clear UX** - User sees progress, knows when to retry download
5. **Graceful fallback** - Unprocessed episodes serve original audio

---

## Testing

```bash
# Get trigger URL for an episode
curl "https://your-server/api/posts/GUID/trigger_link" -H "Cookie: session=..."

# Visit trigger page (should show progress UI)
open "https://your-server/trigger?guid=GUID&feed_token=X&feed_secret=Y"

# Download (should serve audio or redirect)
curl -L "https://your-server/api/posts/GUID/download?feed_token=X&feed_secret=Y"
```
