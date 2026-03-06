# Podly - AI Agent Guidelines

This file contains important context for AI assistants working on this codebase.

## Project Overview

Podly is a podcast ad-removal system. It uses Whisper for transcription and LLMs for ad detection.

**Key documentation**: See `docs/ARCHITECTURE.md` for detailed system architecture.

---

## Database

### Location
- **Local**: `src/instance/sqlite3.db`
- **Docker**: `/app/src/instance/sqlite3.db` (NOT `/app/instance/podly.db`)

### Migrations (Alembic / Flask‑Migrate)

**CRITICAL: Every model change MUST have a corresponding migration file.**

When adding or modifying models in `src/app/models.py`:
1. **ALWAYS create a migration file** in `src/migrations/versions/` immediately after changing models
2. Check existing migrations to find the latest `revision` ID to use as `down_revision`
3. Use descriptive revision IDs (e.g., `f3a4b5c6d7e8_add_user_feed_subscription.py`)

The assistant may generate or modify Alembic/Flask‑Migrate migrations, but must:
- **Create a migration file for EVERY new table, column, or index added to models.py**
- Clearly announce when a schema change requires a migration.
- Keep migrations minimal and focused on the actual model changes made in this PR.
- Never drop or rename tables/columns that contain production data unless explicitly requested and the intent is documented.
- Prefer additive changes (new tables/columns/indexes) over destructive ones.

After editing models, the assistant should:
- **Immediately create the migration file** - do not wait for the user to ask
- Ensure migrations are idempotent, reversible, and match the updated models
- Test that the migration applies cleanly

The assistant must not fabricate migrations for schemas it hasn't actually inspected; it should always base migration content on the current `app/models.py` and existing migration history.

### Migration File Template

```python
"""Description of change

Revision ID: <unique_id>
Revises: <previous_revision_id>
Create Date: <date>
"""
from alembic import op
import sqlalchemy as sa

revision = '<unique_id>'
down_revision = '<previous_revision_id>'
branch_labels = None
depends_on = None

def upgrade():
    # Create table / add column / create index
    pass

def downgrade():
    # Reverse the upgrade
    pass
```

### Manual SQL Migrations in Docker

The Docker container does NOT have `sqlite3` CLI installed. For manual SQL migrations, use Python:

```bash
sudo docker exec podly-pure-podcasts python -c "
import sqlite3
conn = sqlite3.connect('/app/src/instance/sqlite3.db')
cursor = conn.cursor()
cursor.execute('YOUR SQL HERE')
conn.commit()
conn.close()
print('Done!')
"
```

**Example: Making a column nullable in SQLite** (requires table recreation):
```bash
sudo docker exec podly-pure-podcasts python -c "
import sqlite3
conn = sqlite3.connect('/app/src/instance/sqlite3.db')
cursor = conn.cursor()

# SQLite doesn't support ALTER COLUMN, must recreate table
cursor.execute('''CREATE TABLE tablename_new (
    id INTEGER PRIMARY KEY,
    column_to_change INTEGER,  -- removed NOT NULL
    other_column TEXT NOT NULL
)''')
cursor.execute('INSERT INTO tablename_new SELECT * FROM tablename')
cursor.execute('DROP TABLE tablename')
cursor.execute('ALTER TABLE tablename_new RENAME TO tablename')

conn.commit()
conn.close()
print('Migration complete!')
"
```

---

## Prompt Presets

Presets are stored in the database (`prompt_preset` table), not just in code.

### Updating Default Presets

When modifying `src/prompt_presets.py`, the database must also be updated:

```bash
# In Docker container
docker exec podly-pure-podcasts bash -c "cd /app && python -c \"
import sys
sys.path.insert(0, 'src')
from app.extensions import db
from app.models import PromptPreset
from prompt_presets import PRESET_DEFINITIONS
from flask import Flask

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/src/instance/sqlite3.db'
db.init_app(app)

with app.app_context():
    for preset_def in PRESET_DEFINITIONS:
        existing = PromptPreset.query.filter_by(name=preset_def['name']).first()
        if existing:
            existing.system_prompt = preset_def['system_prompt']
            existing.description = preset_def['description']
            existing.min_confidence = preset_def['min_confidence']
    db.session.commit()
    print('Presets updated!')
\""
```

### User-Created Presets

Users can create/edit presets via the UI. These are stored in the database and persist correctly. The init script only affects the 3 default presets (Conservative, Balanced, Aggressive).

### Preset Access Control

**Presets page is admin-only.** Regular users cannot change presets, which prevents one user's preset change from affecting another user's downloads.

### Preset Tracking

When an episode is processed, the active preset ID is stored on the `Post` record (`processed_with_preset_id`). This allows:
- Viewing which preset was used in the episode stats modal (Overview tab)
- Understanding why ad detection behaved a certain way
- Episodes processed before this feature show "Processed before preset tracking was added"

**Important behavior:** If User A processes an episode with "Conservative" preset, and User B later downloads it, User B gets the Conservative-processed version. The preset is locked at processing time, not download time.

### Prompt Design Principles

All presets emphasize flagging **ALL segments within an ad block**, not just the announcement. Key prompt elements:
- "CRITICAL: Flag EVERY segment that is part of an ad"
- Examples showing multiple consecutive segments being flagged
- Clear distinction between ad content and legitimate discussion

### Per-Show Default Preset

Admins can set a custom default preset for individual shows/feeds. This overrides the server-wide active preset for that specific show.

**Database:** `Feed.default_prompt_preset_id` (nullable FK to `prompt_preset`)

**API:**
- `GET /api/feeds` returns `default_prompt_preset` and `effective_prompt_preset` for each feed
- `POST /api/feeds/<feed_id>/default-preset` (admin-only) sets the default preset

**Processing Logic:**
1. If feed has `default_prompt_preset_id` set → use that preset
2. Otherwise → use server-wide active preset
3. If no active preset → fall back to default prompt files

**UI:** In the "Show settings" modal on the Podcasts page, admins see a "Choose custom preset" dropdown.

---

## Frontend

### Theme
Three switchable themes: **Blue** (default), Light, Dark. Key files:
- `frontend/src/theme.ts` - Theme labels, logos, brand names
- `frontend/src/contexts/ThemeContext.tsx` - Theme state (localStorage)
- `frontend/tailwind.config.js` - Custom colors
- `frontend/src/index.css` - Global overrides, blue theme `[data-theme="original"]` selectors

### Logo
Blue-theme logo at `frontend/public/images/logos/original-logo.png` (primary).
Unicorn logo at `frontend/public/images/logos/unicorn-logo.png` (light/dark themes).
Used in sidebar header (`Sidebar.tsx`) and login page (`LoginPage.tsx`).

### Modals
Use `createPortal` from `react-dom` to render modals to `document.body` to avoid z-index issues with parent containers.

### CSS Overrides
Global CSS in `index.css` overrides gray colors with purple tints. Use inline `style={{}}` for elements that need original colors (e.g., inside modals).

### Podcasts Page UI

The Podcasts page (`/podcasts`) displays subscribed feeds and their episodes.

**Feed Header:**
- Feed image, title, author, episode count
- Action buttons: **Podly RSS** (gradient), **Settings**, **Unsubscribe**
- Feed description below header

**Show Settings Dropdown:**
Accessed via the "Settings" button. Opens a dropdown menu with:
- **Auto-process** - Toggle for auto-processing new episodes (auth required)
- **Enable all episodes** - Whitelist all episodes in the feed
- **Disable all episodes** - Remove all episodes from whitelist
- **Refresh feed** - Fetch new episodes from upstream RSS
- **Original RSS feed** - Copy the source RSS URL

The dropdown uses inline styles for solid backgrounds to avoid CSS override issues in dark mode.

### User Statistics
Admin users can view per-user statistics in Settings → User Statistics section:
- Episodes processed per user
- Downloads per user  
- Ad time removed per user
- Recent download history

---

## LLM Configuration

### ⚠️ Groq vs Grok - Don't Get Confused!

These are **completely different companies/products**:

| Name | Company | What it is | Used for |
|------|---------|------------|----------|
| **Groq** | Groq Inc (groq.com) | Fast inference platform | Whisper transcription + LLM |
| **Grok** | xAI (x.ai) | Chatbot/LLM model | LLM only (ad detection) |

- **Groq API key** starts with `gsk_...`
- **Grok (xAI) API key** starts with `xai-...`

### Supported Providers

Podly uses [LiteLLM](https://docs.litellm.ai/) which supports 100+ providers. Recommended options:

| Provider | Model Format | Base URL | Notes |
|----------|--------------|----------|-------|
| **Groq** | `groq/openai/gpt-oss-120b` | *(ignored)* | Fast, free tier, handles both LLM + Whisper |
| **xAI Grok** | `xai/grok-3` | *(optional)* | **Recommended for accuracy**, ~$0.10/episode |
| **OpenAI** | `gpt-4o` | *(default)* | Excellent quality, higher cost |
| **Anthropic** | `anthropic/claude-3-7-sonnet-latest` | *(ignored)* | High quality alternative |
| **Google Gemini** | `gemini/gemini-2.0-flash` | *(ignored)* | Fast, good value |

Models with a provider prefix (e.g. `groq/`, `xai/`, `anthropic/`) are routed automatically by LiteLLM — no Base URL needed.

### Recommended Setup

**Simplest**: Just set `GROQ_API_KEY` - it handles both transcription and ad detection.

**Recommended for accuracy**: Use Groq for Whisper (fast, free) + xAI Grok for LLM (best ad detection):
```bash
GROQ_API_KEY=gsk_...        # For Whisper transcription
LLM_API_KEY=xai-...         # For ad detection
LLM_MODEL=xai/grok-3
WHISPER_TYPE=groq
# OPENAI_BASE_URL is optional — xai/ prefix auto-routes
```

### Model Name Format
- **With provider prefix** (e.g., `groq/...`, `xai/...`): LiteLLM routes automatically, Base URL setting is ignored
- **Without prefix** (e.g., `gpt-4o`): Uses `OPENAI_BASE_URL` if set

### API Key and Base URL
The `api_key` and `api_base` are passed explicitly in completion calls to support providers like xAI that require them.

### LLM Key Profiles (Saved Keys)

Admins can save encrypted API keys as "key profiles" via the Settings page, instead of pasting raw keys each time.

**Database:** `LLMKeyProfile` table (`llm_key_profile`) with columns: `name`, `provider`, `encrypted_api_key`, `api_key_preview`, `openai_base_url`, `default_model`, `last_used_at`.

**Encryption:** Keys are encrypted with Fernet (AES-128-CBC) using a key derived from `SECRET_KEY` via SHA-256. See `src/app/secret_store.py`.

**Dependency:** Requires the `cryptography` Python package (added to Pipfile + Pipfile.lite).

**Key Reference System:** The `llm_api_key` field in `LLMSettings` can hold:
- A direct API key string
- `env:ENV_VAR_NAME` — resolved at runtime from environment
- `profile:ID` — resolved at runtime by decrypting the saved profile

Resolution logic lives in `src/app/llm_key_profiles.py` → `resolve_llm_api_key_reference()`.

**API Endpoints (admin-only):**
- `GET /api/config/llm-options` — returns provider catalog, model list, detected env keys, saved profiles, and current selection
- `POST /api/config/llm-key-profiles` — create a new saved key profile
- `DELETE /api/config/llm-key-profiles/<id>` — delete a saved key profile (clears active selection if in use)

**Provider Catalog:** Defined in `src/app/llm_key_profiles.py` → `LLM_PROVIDER_CATALOG`. Includes Groq, xAI, OpenAI, Anthropic, Google Gemini, and Custom.

---

## Processing Flow

**On-Demand**: Episodes are NOT auto-processed when enabled. Processing only triggers when:
1. User clicks "Process" button in web UI
2. User taps trigger link in podcast app (RSS `<item><link>` and episode description link to `/trigger` page)

### Trigger Page Architecture

The RSS feed includes a trigger URL in each episode's `<item><link>` and description:
```
/trigger?guid=X&feed_token=Y&feed_secret=Z
```

**User flow:**
1. User taps "Process this episode (remove ads)" link in episode description
2. Browser opens trigger page showing processing progress
3. When complete, page shows "Episode Ready" with instruction to close tab
4. User closes tab and returns to podcast app
5. User refreshes feed and plays ad-free episode

**Trigger page states:**
- `processing` - Job running, shows progress bar with step indicators
- `ready` - Episode processed, shows "Episode Ready" + "Close this tab now"
- `failed` - Processing failed, shows error message
- `error` - Auth failed or episode not found

**Key design**: Download endpoint (`/api/posts/<guid>/download`) does NOT trigger processing - it only serves audio (processed or original). This prevents accidental mass processing from RSS polling.

**RSS description CTA**: Each episode description includes a canonical CTA block wrapped in `<!-- PODLY_TRIGGER_START -->` / `<!-- PODLY_TRIGGER_END -->` markers. The `inject_trigger_cta()` function in `src/app/feeds.py` handles idempotent injection.

See `docs/TRIGGER_ARCHITECTURE.md` for full technical details.

### Episode States
- **Enabled** (blue badge) - Eligible for processing, but not yet processed
- **Disabled** (gray dashed badge) - Skipped entirely, won't appear in RSS feed
- **Ready** (green badge) - Processed and ready to play/download

### Buttons
- **Enable/Disable** - Toggle whether episode is eligible for processing
- **Process** (purple) - Start processing an enabled episode that hasn't been processed
- **Reprocess** (orange) - Re-process an already-processed episode (clears existing data)

### Auto-Cleanup
Processed files are automatically deleted after 14 days (configurable in Settings → App Settings).

---

## Docker

### Container: `podly-pure-podcasts`

### Common Commands
```bash
docker logs -f podly-pure-podcasts          # View logs
docker restart podly-pure-podcasts          # Restart
docker exec -it podly-pure-podcasts bash    # Shell access
```

### Database Access in Docker
The running app locks the database. To run scripts:
1. Stop the app, OR
2. Use a minimal Flask app that doesn't start the scheduler (see preset update script above)

---

## Security

### Authentication
- **Session-based auth** with HttpOnly, SameSite=Lax cookies
- **bcrypt** password hashing (12 rounds)
- **Rate limiting** with exponential backoff on failed auth attempts (max 5 min)
- **Feed tokens** for RSS access - SHA-256 hashed, timing-safe comparison
- **Password validation** enforces minimum 8 characters on creation/change
- **Login endpoint** returns generic error messages to prevent user enumeration
- **Legacy mutating routes** (`/set_whitelist`, `/toggle-whitelist-all`) require POST + session auth

### Feed Token Secrets
New feed tokens use **deterministic derived secrets** (HMAC-SHA256 of `SECRET_KEY` + `token_id`) instead of storing plaintext secrets in the DB. Old tokens with stored `token_secret` continue to work. See `src/app/auth/feed_tokens.py`.

### Authorization
- **Admin-only routes**: Settings, Presets, User Management, LLM Key Profiles
- Backend enforces admin checks via `_require_admin()` helper
- Frontend hides admin UI but backend is the source of truth

### Environment Variables
| Variable | Purpose | Required |
|----------|---------|----------|
| `PODLY_SECRET_KEY` | Session + token encryption key | **Required for production** |
| `REQUIRE_AUTH` | Enable authentication | Yes for multi-user |
| `PODLY_ADMIN_USERNAME` / `PODLY_ADMIN_PASSWORD` | Initial admin credentials | Yes if auth enabled |
| `SESSION_COOKIE_SECURE` | Force secure cookies (defaults to `true` when auth enabled) | Set `false` for HTTP-only dev |
| `CORS_ORIGINS` | Allowed CORS origins | Production only |

### Production Recommendations
1. Set `PODLY_SECRET_KEY` to a stable secret (sessions persist across restarts, feed tokens derived from it)
2. Use HTTPS (reverse proxy like nginx/Caddy)
3. Set `CORS_ORIGINS` to your domain only
4. Use a strong admin password (minimum 8 characters enforced at bootstrap)

### RSS Feed Authentication
When auth is enabled, RSS feeds require tokens. The "Subscribe to Podly RSS" button automatically generates a tokenized URL that podcast apps can use without login.

---

## Feed Subscriptions

### Overview
Users subscribe to feeds to see them in their Podcasts page. This provides per-user feed filtering and privacy controls.

### Database Model
`UserFeedSubscription` table tracks subscriptions with fields:
- `user_id` - The subscribing user
- `feed_id` - The feed being subscribed to
- `subscribed_at` - Timestamp
- `is_private` - Boolean, hides subscription from other users
- `auto_download_new_episodes` - Boolean, enables auto-processing of new episodes

### Subscription Types
- **Public subscription**: Visible to other users in "Browse Podcasts on Server"
- **Private subscription**: Hidden from other users, but visible to admin for usage tracking

### Feed Visibility Rules
A feed appears in "Browse Podcasts on Server" if:
1. User is already subscribed (public or private), OR
2. At least one other user has a PUBLIC subscription

Feeds with only private subscribers are hidden from non-subscribers.

### Admin Subscriptions Page
Admins can view all subscriptions at `/subscriptions`:
- Shows all feeds with subscriber counts
- Lists all subscribers (including private ones, marked with eye icon)
- Displays processing stats per feed
- **Status badges** on each feed:
  - **Auto** (green) - Auto-process enabled by at least one user
  - **Public** (blue) - Has public subscribers, visible in Browse Podcasts
  - **Private Only** (amber) - All subscribers are private
  - **Hidden** (gray) - Admin has hidden the feed
- **Settings button** (gear icon) on each feed card opens modal with:
  - **Hide from Browse** toggle - Admin can hide feed from Browse Podcasts
  - **Auto-Process** toggle - Admin can disable auto-process for all users

### Delete Behavior
When a user clicks "Delete" on a feed:
- **If other subscribers exist**: Just unsubscribes the user
- **If user is last subscriber**: Fully deletes the feed and all data

### Auto-Subscribe
When a user adds a new feed, they are automatically subscribed to it.

### Auto-Process New Episodes

Per-feed toggle to automatically process new episodes when they are released. (Renamed from "Auto-Download" in the UI for clarity.)

**Behavior:**
- Default is **OFF** for all users
- If **any user** enables auto-process for a feed, new episodes are auto-processed for **everyone**
- Other users see the toggle disabled with note: "Enabled by another user"
- When the enabling user disables it (or unsubscribes), auto-process stops (unless another user has it enabled)

**UI Location:** "Show settings" modal on the Podcasts page (only visible when auth is enabled)

**Backend:** When feeds are refreshed and new episodes are discovered, if any subscriber has `auto_download_new_episodes=True`, those episodes are automatically whitelisted and processing jobs are started.

---

## Migrations

### Running Migrations in Docker

**IMPORTANT:** The standard `flask db upgrade` command often fails in Docker because the Flask app startup initializes the scheduler and jobs manager, which conflicts with the running container's SQLite locks.

**Recommended approach:** Apply migrations directly via Python script:

```bash
docker exec <container-name> bash -lc 'python - <<"PY"
import sqlite3

conn = sqlite3.connect("/app/src/instance/sqlite3.db")
cursor = conn.cursor()

# Example: Add a column
# cursor.execute("ALTER TABLE table_name ADD COLUMN column_name TYPE DEFAULT value")

# Update alembic_version to the new revision
# cursor.execute("UPDATE alembic_version SET version_num = ?", ("new_revision_id",))

conn.commit()
conn.close()
print("Migration complete!")
PY'
```

Then restart the container:
```bash
docker restart <container-name>
```

### Current Migration Head

**Revision:** `m0n1o2p3q4r5` (Add llm_key_profile table)

### Migration History (recent)

| Revision | Description |
|----------|-------------|
| `m0n1o2p3q4r5` | Add `llm_key_profile` table for encrypted saved API keys |
| `l9m0n1o2p3q4` | Make `feed_access_token.feed_id` nullable (combined feed tokens) |
| `k8l9m0n1o2p3` | Remove unique constraint from `post.download_url` (allows duplicate audio URLs) |
| `j7k8l9m0n1o2` | Add `feed_id` to `user_download` and make `post_id` nullable |
| `i6j7k8l9m0n1` | Add `event_type` to `user_download` |
| `g4h5i6j7k8l9` | Add `auth_type` and `decision` columns to `user_download` |
| `h5i6j7k8l9m0` | Add `trigger_source` to `processing_job` |
| `c3d4e5f6a7b8` | Add `is_hidden` to `feed` table |
