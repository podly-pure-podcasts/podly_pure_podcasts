# Trigger-Based Processing Architecture

This document explains the on-demand processing architecture for Podly, covering the conceptual model, why specific design decisions were made, and how to test the system.

## Important Auth Assumption

This trigger flow assumes `REQUIRE_AUTH=true` and tokenized feed URLs.

- With `REQUIRE_AUTH=true`: RSS links include `feed_token`/`feed_secret`, and podcast apps can use `/trigger` and download links as documented below.
- With `REQUIRE_AUTH=false`: feed links are not tokenized. In the current release, `/trigger` and `/api/posts/<guid>/download` still expect token/session auth, so podcast-app trigger/download behavior is limited.

---

## Conceptual Model

Podly separates four distinct concerns:

| Layer | Responsibility | Mutates State? |
|-------|----------------|----------------|
| **Discovery** | RSS feeds expose episodes to podcast apps | No |
| **User Intent** | `/trigger` page lets users explicitly request processing | Yes (creates jobs) |
| **Processing** | Jobs system transcribes audio and detects ads | Yes (creates files) |
| **Delivery** | `/api/posts/<guid>/download` serves processed audio | No |

This separation ensures that passive operations (RSS fetching, download probes) never accidentally trigger expensive processing jobs.

---

## The Core Invariant

> **Jobs are created only from a page a human intentionally visits.**

This single rule eliminates:

- Background probes from podcast apps triggering jobs
- App-specific behaviour quirks causing processing storms
- Retry storms from apps re-fetching failed downloads
- User-Agent detection hacks
- Future regressions when podcast apps change behaviour

---

## Why Downloads Never Trigger Jobs

**Important:** The download endpoint (`/api/posts/<guid>/download`) is intentionally non-mutating.

Processing jobs are created *only* via the `/trigger` page. This prevents unintended processing from:

- RSS readers prefetching enclosures
- Podcast apps probing file sizes (HEAD requests, Range requests)
- Bots and crawlers
- Background sync operations

### Download Endpoint Behaviour

| Scenario | Response |
|----------|----------|
| Episode processed | `200 OK` + audio file |
| Episode not processed, job running | `503 Service Unavailable` + `Retry-After: 120` |
| Episode not processed, no job | `503 Service Unavailable` + `Retry-After: 300` |

The download endpoint **never** creates jobs. Users must visit `/trigger` to start processing.

---

## Why `/trigger` Exists

The `/trigger` endpoint serves as the explicit user intent boundary:

1. **Capability-based auth**: Uses feed-scoped tokens (not session cookies)
2. **User-friendly**: Shows progress bar, polls for completion, offers download
3. **Rate-limited**: 10-minute cooldown between job attempts per episode
4. **Observable**: Logs all trigger attempts with `[TRIGGER_*]` markers

### Trigger Page States

| State | Description |
|-------|-------------|
| `ready` | Episode already processed, shows download button |
| `processing` | Job running, shows progress bar with polling |
| `queued` | Job pending, shows progress bar |
| `cooldown` | Recent job attempt, shows wait message |
| `error` | Auth failed or episode not found |

### How It Works

1. User clicks episode link in podcast app (RSS `<link>` element)
2. Browser opens `/trigger?guid=...&feed_token=...&feed_secret=...`
3. Page validates token, creates job if needed, shows progress
4. User waits for processing to complete
5. Download button appears when ready

---

## Combined RSS Behaviour

The combined feed (`/feed/combined`) aggregates episodes from all subscribed podcasts.

### Key Properties

- **Read-only**: Fetching the feed never triggers processing
- **Per-episode tokens**: Each `<item>` has feed-scoped tokens for its source feed
- **Trigger links**: Each `<item><link>` points to `/trigger` with feed-scoped tokens
- **Combined tokens cannot trigger**: Tokens with `feed_id=NULL` are rejected by `/trigger`

### Why Combined Tokens Can't Trigger

Combined feed tokens are designed for read-only access. They can:
- Fetch the combined RSS feed
- Download already-processed episodes

They cannot:
- Trigger processing (403 Forbidden)
- Access `/api/trigger/status`

This prevents a single compromised combined token from triggering processing storms across all feeds.

---

## Token Types

| Token Type | `feed_id` | Can Trigger? | Use Case |
|------------|-----------|--------------|----------|
| Feed-scoped | `123` | Yes | Per-show RSS, trigger links |
| Combined | `NULL` | No | Combined RSS feed only |

---

## Endpoints Reference

### Public (Token Auth)

| Endpoint | Method | Auth | Creates Jobs? |
|----------|--------|------|---------------|
| `/trigger` | GET | Feed token | Yes (feed-scoped only) |
| `/api/trigger/status` | GET | Feed token | No |
| `/api/posts/<guid>/download` | GET | Feed token | No |
| `/feed/combined` | GET | Combined token | No |
| `/feed/<id>` | GET | Feed token | No |

### Web UI (Session Auth)

| Endpoint | Method | Auth | Creates Jobs? |
|----------|--------|------|---------------|
| `/api/posts/<guid>/process` | POST | Session | Yes |
| `/api/posts/<guid>/reprocess` | POST | Session | Yes |
| `/api/feeds/combined/episodes` | GET | Session | No |

---

## Testing Locally

### 1. Verify RSS Trigger Links

```bash
# Fetch combined feed and check for trigger links
curl -s "http://localhost:5001/feed/combined?feed_token=...&feed_secret=..." | grep -o '<link>[^<]*</link>' | head -5
```

Expected: Links should be `https://your-domain.com/trigger?guid=...&feed_token=...&feed_secret=...`

### 2. Verify Download Doesn't Create Jobs

```bash
# Pick an unprocessed episode GUID
GUID="your-episode-guid"

# Count jobs before
sqlite3 src/instance/sqlite3.db "SELECT COUNT(*) FROM processing_job WHERE post_guid='$GUID'"

# Hit download endpoint
curl -I "http://localhost:5001/api/posts/$GUID/download?feed_token=...&feed_secret=..."

# Count jobs after (should be same)
sqlite3 src/instance/sqlite3.db "SELECT COUNT(*) FROM processing_job WHERE post_guid='$GUID'"
```

### 3. Verify Trigger Creates Jobs

```bash
# Hit trigger endpoint
curl "http://localhost:5001/trigger?guid=$GUID&feed_token=...&feed_secret=..."

# Check job was created
sqlite3 src/instance/sqlite3.db "SELECT id, status FROM processing_job WHERE post_guid='$GUID' ORDER BY created_at DESC LIMIT 1"
```

### 4. Use Verification Script

```bash
python scripts/verify_trigger_links.py \
  --combined-url "https://your-domain.com/feed/combined?feed_token=...&feed_secret=..." \
  --expected-domain your-domain.com
```

---

## Common Pitfalls (And Why They're Prevented)

### Pitfall 1: Podcast App Triggers Processing Storm

**Scenario**: User subscribes to combined feed, app prefetches all enclosures, triggers 100 jobs.

**Prevention**: Download endpoint never creates jobs. User must explicitly visit `/trigger`.

### Pitfall 2: Combined Token Used to Trigger Jobs

**Scenario**: Attacker gets combined feed URL, uses it to trigger processing for all episodes.

**Prevention**: Combined tokens (`feed_id=NULL`) are rejected by `/trigger` with 403.

### Pitfall 3: Bot Crawls Trigger Links

**Scenario**: Search engine bot follows `<link>` elements in RSS, triggers jobs.

**Prevention**: 
- Trigger requires valid feed token
- 10-minute cooldown between attempts
- Jobs are idempotent (existing job = no new job)

### Pitfall 4: User Accidentally Reprocesses

**Scenario**: User clicks trigger link for already-processed episode.

**Prevention**: Trigger page shows "Episode Ready" with download button, no new job created.

---

## Observability

All trigger-related actions are logged to stderr with markers:

| Marker | Description |
|--------|-------------|
| `[TRIGGER_HIT]` | Request received |
| `[TRIGGER_AUTH]` | Token validated |
| `[TRIGGER_JOB]` | Job created/found |
| `[TRIGGER_RETURN]` | Response sent |
| `[TRIGGER_STATUS]` | Status poll received |
| `[DOWNLOAD_HIT]` | Download request received |
| `[DOWNLOAD_RETURN]` | Download response sent |

Example log flow for successful trigger:
```
[TRIGGER_HIT] guid=abc123 token_id=tok_xyz
[TRIGGER_AUTH] guid=abc123 feed_id=5 user_id=1
[TRIGGER_JOB] guid=abc123 action=create user_id=1
[TRIGGER_JOB] guid=abc123 action=created job_id=job_456
```

---

## Architecture Diagram

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Podcast App   │     │    Browser      │     │    Web UI       │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │ GET /feed/combined    │                       │
         │ (read-only)           │                       │
         ▼                       │                       │
┌─────────────────┐              │                       │
│   RSS Feed      │              │                       │
│   <link> →      │──────────────┘                       │
│   /trigger      │   User clicks link                   │
└─────────────────┘              │                       │
                                 ▼                       │
                    ┌─────────────────┐                  │
                    │   /trigger      │◄─────────────────┘
                    │   (creates job) │   "Process now" button
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Jobs System   │
                    │   (processing)  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   /download     │
                    │   (serves file) │
                    └─────────────────┘
```

---

## Summary

The trigger-based architecture ensures:

1. **RSS is passive** - No mutations on feed fetch
2. **Downloads are passive** - No mutations on audio fetch
3. **Processing requires intent** - Only `/trigger` creates jobs
4. **Combined feed is safe** - Read-only, cannot trigger
5. **System is observable** - All actions logged with clear markers

This design is *explainable*, *documentable*, and *defensible*.
