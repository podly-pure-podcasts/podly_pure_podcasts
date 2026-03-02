# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Podly Unicorn is a podcast ad-removal web application. It uses Whisper for transcription and LLMs for ad detection, then removes detected ad segments from audio files. Users subscribe to modified RSS feeds that serve ad-free episodes.

**Tech Stack:** Python/Flask backend, React/TypeScript frontend, SQLite database, Docker deployment.

## Common Commands

### Backend (Python)

```bash
# Install dependencies
pipenv install --dev

# Run all tests
pipenv run pytest --disable-warnings

# Run single test file
pipenv run pytest src/tests/test_feeds.py --disable-warnings

# Run specific test
pipenv run pytest src/tests/test_feeds.py::test_function_name --disable-warnings

# Type checking
pipenv run mypy src

# Linting
pipenv run pylint src --ignore=migrations,tests

# Formatting
pipenv run black src
pipenv run isort src
```

### Frontend (React/TypeScript)

```bash
cd frontend
npm install
npm run dev      # Development server (http://localhost:5173)
npm run build    # Production build to dist/
npm run lint     # ESLint
```

### Docker

```bash
docker compose up -d --build     # Start/rebuild
docker compose restart           # Restart
docker compose down              # Stop
docker logs -f podly-pure-podcasts  # View logs
```

### Database Migrations

```bash
./scripts/create_migration.sh "description"  # Create new migration
./scripts/upgrade_db.sh                      # Apply migrations
./scripts/downgrade_db.sh                    # Rollback migration
```

## Architecture

### Directory Structure

- `src/app/` - Flask application (routes, models, auth)
- `src/podcast_processor/` - Core processing pipeline (download, transcribe, classify, cut audio)
- `src/shared/` - Shared utilities and configuration
- `src/tests/` - Test suite with fixtures in `conftest.py`
- `src/migrations/` - Alembic database migrations
- `frontend/src/` - React application (pages, components, services)

### Processing Pipeline

1. User triggers processing via web UI or RSS trigger link
2. Download original podcast audio
3. Transcribe with Whisper → `transcript_segment` records
4. Send segments to LLM for ad classification → `identification` records
5. Filter by `min_confidence` threshold
6. Remove ad segments with FFmpeg (with fades)
7. Serve processed audio via RSS feed

### Key Models (src/app/models.py)

- `Feed` - Podcast RSS subscriptions
- `Post` - Individual episodes
- `TranscriptSegment` - Whisper transcription segments
- `Identification` - LLM ad/content classifications
- `PromptPreset` - Ad detection prompt configurations
- `User`, `UserFeedSubscription` - Multi-user auth and subscriptions

### Database

- Location: `src/instance/sqlite3.db` (local), `/app/src/instance/sqlite3.db` (Docker)
- **Every model change requires a migration file** in `src/migrations/versions/`
- Check existing migrations for the latest `revision` ID to use as `down_revision`

## Testing Conventions

- Use pytest fixtures from `src/tests/conftest.py`
- Create custom mock classes for SQLAlchemy models (avoid `MagicMock(spec=ModelClass)`)
- Prefer dependency injection via constructor over patching
- Use `monkeypatch` for external resources, `tmp_path` for file operations

## LLM Configuration

**Groq** (groq.com) is a fast inference platform. **Grok** (x.ai) is xAI's LLM model. These are different companies:
- Groq API keys start with `gsk_...`
- Grok (xAI) API keys start with `xai-...`

LLM provider is configured via `LLM_MODEL` with LiteLLM format (e.g., `groq/openai/gpt-oss-120b`, `xai/grok-3`).

## Prompt Presets

Presets are stored in the database (`prompt_preset` table). When modifying `src/prompt_presets.py`, the database must also be updated. See AGENTS.md for the update script.

Admin-only: Regular users cannot change presets.

## RSS Feed Behavior

- Episodes are processed **on-demand only** (user clicks trigger link)
- Download endpoint does NOT trigger processing
- RSS description includes trigger CTA wrapped in `<!-- PODLY_TRIGGER_START -->` markers
