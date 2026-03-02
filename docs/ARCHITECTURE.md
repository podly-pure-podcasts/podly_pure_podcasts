# Podly Unicorn Architecture

This document describes the key architectural components and data flows in Podly Unicorn.

## Overview

Podly Unicorn is a podcast ad-removal system that:
1. Subscribes to podcast RSS feeds
2. Transcribes episodes using Whisper (local, remote, or Groq)
3. Detects ads using an LLM with configurable prompt presets
4. Serves a clean RSS feed with ads removed

## Directory Structure

```
podly_pure_podcasts/
├── frontend/                 # React frontend (Vite + TypeScript)
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   ├── contexts/         # React contexts (AudioPlayer, etc.)
│   │   ├── pages/            # Page components (Dashboard, Podcasts, Jobs, Config)
│   │   ├── services/         # API client
│   │   └── types/            # TypeScript type definitions
│   └── tailwind.config.js    # Tailwind CSS config with unicorn theme
│
├── src/                      # Python backend
│   ├── app/                  # Flask application
│   │   ├── routes/           # API route handlers
│   │   ├── models.py         # SQLAlchemy database models
│   │   ├── extensions.py     # Flask extensions (db, migrate, etc.)
│   │   └── __init__.py       # App factory and scheduler setup
│   │
│   ├── podcast_processor/    # Core processing logic
│   │   ├── ad_classifier.py  # LLM-based ad detection
│   │   ├── audio.py          # Audio manipulation (ffmpeg)
│   │   ├── transcription.py  # Whisper transcription
│   │   └── podcast_processor.py  # Main processing orchestrator
│   │
│   ├── migrations/           # Alembic database migrations
│   ├── scripts/              # Utility scripts
│   │   └── init_prompt_presets.py  # Initialize default presets
│   └── prompt_presets.py     # Default prompt preset definitions
│
├── instance/                 # Instance-specific data (gitignored)
│   └── sqlite3.db            # SQLite database (in Docker: /app/src/instance/)
│
└── docs/                     # Documentation
```

## Database Schema

### Key Tables

| Table | Purpose |
|-------|---------|
| `feed` | Podcast RSS feed subscriptions |
| `post` | Individual podcast episodes |
| `transcript_segment` | Whisper transcription segments |
| `identification` | LLM ad/content classifications |
| `model_call` | LLM API call logs for debugging |
| `prompt_preset` | Ad detection prompt configurations |
| `processing_statistics` | Per-episode processing stats |
| `processing_job` | Background job queue |
| `llm_settings` | LLM API configuration |
| `whisper_settings` | Whisper configuration |

### Database Location

- **Local development**: `src/instance/sqlite3.db`
- **Docker**: `/app/src/instance/sqlite3.db`

## Prompt Presets

Presets control how aggressively the LLM detects ads.

### Default Presets

| Name | Aggressiveness | Min Confidence | Use Case |
|------|----------------|----------------|----------|
| Conservative | Low | 0.8 | Preserve content, only obvious ads |
| Balanced | Medium | 0.7 | **Default** - Good balance |
| Aggressive | High | 0.55 | Catch more ads, may remove some content |

### Prompt Design

All presets emphasize flagging **complete ad blocks**, not just announcements. Key prompt elements:
- "CRITICAL: Flag EVERY segment that is part of an ad"
- Examples showing multiple consecutive segments being flagged
- Clear distinction between ad content and legitimate discussion

**Note:** When you activate a preset, it automatically updates the Output Settings `min_confidence` to match. This ensures the confidence threshold is consistent between ad detection and audio processing.

### Preset Structure

```python
{
    "name": "Balanced",
    "description": "Recommended for most podcasts...",
    "aggressiveness": "balanced",  # conservative|balanced|aggressive
    "system_prompt": "...",        # Instructions for the LLM
    "user_prompt_template": "...", # Template with {transcript} placeholder
    "min_confidence": 0.7,         # Threshold for ad classification
    "is_active": True,             # Only one preset can be active
    "is_default": True,            # Cannot be deleted
}
```

### Updating Presets

**Via UI**: Settings → Presets (changes persist immediately)

**Via script** (updates default presets only):
```bash
# In Docker
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

## Processing Flow

### Episode Processing (On-Demand)

```
1. Trigger (podcast app request OR manual "Process" click)
       ↓
2. Check if episode is enabled (whitelisted)
       ↓ (if disabled, skip)
3. Download original audio
       ↓
4. Transcribe with Whisper → transcript_segment records
       ↓
5. Batch segments and send to LLM with active preset's prompt
       ↓
6. LLM returns JSON with ad classifications → identification records
       ↓
7. Filter segments by min_confidence threshold
       ↓
8. Remove ad segments from audio (ffmpeg)
       ↓
9. Save processed audio, update post.has_processed_audio = True
```

### Key Point: On-Demand Processing

Episodes are **NOT** processed automatically when enabled. Processing occurs:
- When a podcast app requests the episode from the Podly RSS feed
- When you manually click "Process" in the web UI

This saves compute resources and API costs.

## API Routes

### Feeds & Episodes
- `GET /api/feeds` - List all feeds
- `POST /api/feeds` - Add new feed
- `GET /api/feeds/<id>/posts` - List episodes
- `POST /api/posts/<guid>/process` - Start processing
- `POST /api/posts/<guid>/reprocess` - Clear and reprocess
- `GET /api/posts/<guid>/download` - Download processed audio

### Presets
- `GET /api/presets` - List all presets
- `POST /api/presets` - Create custom preset
- `PUT /api/presets/<id>` - Update preset
- `DELETE /api/presets/<id>` - Delete custom preset
- `POST /api/presets/<id>/activate` - Set active preset

### Configuration
- `GET /api/config` - Get all settings
- `PUT /api/config/llm` - Update LLM settings
- `PUT /api/config/whisper` - Update Whisper settings

## LLM Configuration

### Supported Providers

Podly uses [LiteLLM](https://docs.litellm.ai/) which supports 100+ providers:

| Provider | Format | Example | Notes |
|----------|--------|---------|-------|
| **Groq** | `groq/<model>` | `groq/openai/gpt-oss-120b` | Fast, cheap |
| **xAI Grok** | `xai/<model>` | `xai/grok-3` | High quality, `xai/` prefix auto-routes |
| **OpenAI** | `<model>` or `openai/<model>` | `gpt-4o` | Excellent quality |
| **Anthropic** | `anthropic/<model>` | `anthropic/claude-3-sonnet` | High quality |
| **Ollama** | `ollama/<model>` | `ollama/llama3` | Local, free |

### Model Name Format

- **With provider prefix** (e.g., `groq/...`, `xai/...`): LiteLLM routes automatically
- **Without prefix**: Uses `OPENAI_BASE_URL` if set, otherwise OpenAI default

### API Key Handling

The `api_key` and `api_base` are passed explicitly in LiteLLM completion calls. This ensures providers like xAI that require explicit authentication work correctly.

### xAI Grok Configuration

```bash
LLM_API_KEY=xai-your-api-key
LLM_MODEL=xai/grok-3
# OPENAI_BASE_URL is optional — xai/ prefix auto-routes
```

## Frontend Theme

The "Unicorn" theme uses a pastel color palette defined in:
- `frontend/tailwind.config.js` - Custom colors
- `frontend/src/index.css` - Global CSS overrides and animations

Key CSS classes:
- `.unicorn-card` - Hover effects for cards
- `.rainbow-text` - Animated gradient text
- `.unicorn-glow` - Soft glow effect
- `.modal-content` - Reset colors inside modals

## Docker

### Container Name
`podly-pure-podcasts`

### Key Paths
- App: `/app`
- Source: `/app/src`
- Database: `/app/src/instance/sqlite3.db`
- Processed audio: `/app/src/instance/processed/`

### Useful Commands

```bash
# View logs
docker logs -f podly-pure-podcasts

# Restart
docker restart podly-pure-podcasts

# Shell access
docker exec -it podly-pure-podcasts bash

# Run Python in app context
docker exec -it podly-pure-podcasts bash -c "cd /app && python -c '...'"
```

## Audio Processing

### Ad Removal

When removing ads from audio, Podly uses ffmpeg with two approaches:

1. **Complex filter** (default): Uses audio fades for smooth transitions between content segments
2. **Simple fallback**: If the complex filter fails (can happen with many ad segments), falls back to a simpler concat approach without fades

The fallback is automatic - if you see "Complex filter failed, trying simple approach" in logs, this is normal.

---

## Environment Variables

See `.env.local.example` for all options. Key variables:

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | API key for LLM provider |
| `LLM_MODEL` | Model name with optional provider prefix (e.g., `xai/grok-3`) |
| `OPENAI_BASE_URL` | Custom API endpoint (e.g., `https://api.x.ai/v1` for xAI) |
| `WHISPER_TYPE` | `local`, `remote`, or `groq` |
| `WHISPER_API_KEY` | API key for Whisper (can be same as GROQ_API_KEY) |
| `GROQ_API_KEY` | Required if using Groq for Whisper |

---

*Last updated: December 2025*
