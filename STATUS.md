# Podly - Project Status

---

## Current Version

**Latest Commit**: `a720386` (docs: update AGENTS.md with current trigger page UX)  
**Date**: 2026-01-08  
**Branch**: `main`

---

## Recent Features (Last 30 Days)

### ✅ Completed

- **Trigger-based Processing Architecture** - Episodes processed only when user explicitly taps trigger link
- **Improved Trigger Page UX** - "Episode Ready" state with clear instructions, better contrast
- **RSS Description Deduplication** - Single canonical CTA block with PODLY_TRIGGER markers
- **ProcessingProgressUI Cleanup** - Removed View Job links, improved dark mode contrast
- **Documentation Updates** - README, User Guide, and AGENTS.md updated for new flow

### 🔄 In Progress

- None currently

---

## Known Issues

### 🐛 Minor Issues

- Some hosts (e.g., Podtrac) can return HTTP 403 when running on datacenter IPs, blocking downloads.  
  See: docs/PROXY_DOWNLOADS.md

### 🚧 Limitations

- Episodes must be manually triggered (by design for resource efficiency)
- No automatic processing of entire backlog (intentional)

---

## Upcoming Changes

### Planned Features

- None currently planned

### Technical Debt

- Consider migration script to clean existing episode descriptions with duplicate CTAs

---

## System Health

### Database

- **Current Migration Head**: `c3d4e5f6a7b8` (Add is_hidden to feed)
- **All migrations**: Applied successfully

### Dependencies

- **Frontend**: React 18, TypeScript, Tailwind CSS
- **Backend**: Flask, SQLAlchemy, Alembic
- **Processing**: Whisper (Groq), LLM (Groq/xAI/OpenAI), FFmpeg

### Performance

- **Processing**: On-demand only, no background jobs
- **Storage**: Auto-cleanup after 14 days (configurable)
- **RSS**: Combined feed aggregates all subscriptions efficiently

---

## Migration Requirements

### For New Installations

- Use Docker Compose (recommended)
- Configure API keys (Groq for free tier, xAI Grok for accuracy)
- Set up authentication for multi-user

### For Upgrades

- Always pull latest code before upgrading
- Database migrations are automatic on container restart
- Check STATUS.md for any manual migration steps

---

## Support

- **Issues**: [GitHub Issues](https://github.com/podly-pure-podcasts/podly_pure_podcasts/issues)
- **Community**: [Discord](https://discord.gg/FRB98GtF6N)
- **Documentation**: See README.md and docs/ folder

---

*Last updated: 2026-01-08*
