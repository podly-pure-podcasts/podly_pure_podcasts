<div align="center">
  <img src="frontend/public/images/logos/unicorn-logo.png" alt="Podly Unicorn" width="200" />
  <h1>Podly Unicorn</h1>
  
  <p>
    <a href="https://github.com/lukefind/podly-unicorn"><img src="https://img.shields.io/badge/GitHub-podly--unicorn-purple?logo=github" alt="GitHub"></a>
    <a href="https://github.com/jdrbc/podly_pure_podcasts/blob/main/LICENCE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License"></a>
    <a href="https://t.me/+AV5-w_GSd2VjNjBk"><img src="https://img.shields.io/badge/Telegram-Join%20Community-229ED9?logo=telegram" alt="Telegram"></a>
  </p>
</div>

---

## What is Podly Unicorn?

Podly Unicorn automatically removes advertisements from podcasts using AI. Add your favorite shows, and Podly creates ad-free RSS feeds you can subscribe to in any podcast app.

This is a fork of [Podly Pure Podcasts](https://github.com/jdrbc/podly_pure_podcasts) with significant UI/UX improvements and new features.

<div align="center">
  <img src="frontend/public/images/screenshots/dashboard-desktop.png" alt="Podly Unicorn Dashboard" width="700" />
  <p><em>Dashboard showing podcast statistics and ad removal progress</em></p>
</div>

<div align="center">
  <table>
    <tr>
      <td><img src="frontend/public/images/screenshots/podcasts-mobile.png" alt="Mobile View" width="300" /></td>
      <td><img src="frontend/public/images/screenshots/processed mobile.png" alt="Processed Episode" width="300" /></td>
    </tr>
    <tr>
      <td align="center"><em>Mobile podcasts view</em></td>
      <td align="center"><em>Processed episode details</em></td>
    </tr>
  </table>
</div>

---

## Updates from Original App

### 🎨 Completely Redesigned UI
- Pastel unicorn theme with purple/pink gradients (light & dark mode)
- Episode-specific thumbnails in RSS feeds (when available from source)

### 🆕 First-Time User Onboarding
- Interactive tutorial on first login
- Step-by-step guide: find podcasts, enable episodes, subscribe in your app
- Explains auto-enable, auto-process, and on-demand processing
- "Replay Tutorial" option in Help modal

### 👥 Multi-User Authentication System
- Per-user feed subscriptions - each user sees only their podcasts
- Private subscriptions - hide your podcasts from other users
- Browse Podcasts on Server - discover feeds other users have added (unless made private)
- User-specific dashboard stats - see your own episodes processed and ad time saved
- Request access / signup flow with admin approval

### 📻 All-in-One Combined Feed
- Single RSS feed with all your subscribed podcasts combined
- Add one feed URL to your podcast app, get all your ad-free shows
- Feed uses Podly Unicorn logo, episodes keep their original artwork
- Click "All-in-One Podly RSS" button on Podcasts page to copy the URL

### 🎛️ Prompt Presets System
- 3 built-in presets: Conservative, Balanced, Aggressive
- Custom presets - create your own ad detection prompts
- Per-show preset overrides - different presets for different podcasts
- Preset tracking - see which preset was used for each episode

### 📊 Enhanced Statistics & Monitoring
- Per-user statistics (admin) - episodes processed, downloads, ad time removed
- Processing progress indicators on episode cards

### ⚙️ Admin Controls
- Feed visibility controls - hide sensitive feeds from browse page
- Disable auto-process for all users on a feed
- Feed status badges - Public, Private, Hidden, Auto indicators
- User management - view all subscriptions and usage
- Database maintenance tools - repair processed paths after migrations
- Signup controls - enable/disable user registration

### 🔄 Auto-Process New Episodes
- Per-feed toggle to automatically process new episodes
- Shared across users - if anyone enables it, new episodes auto-process
- Visual indicators showing which feeds have auto-process enabled

### 📱 Mobile Optimizations
- Fully responsive design for phones and tablets
- Touch-friendly controls and modals
- Optimized layouts for small screens

---

## How It Works

1. **Add a podcast** — Paste an RSS feed URL or search the built-in podcast catalog
2. **Subscribe in your podcast app** — Copy the Podly RSS feed URL and add it to your app
3. **Trigger processing** — Tap the episode link in your podcast app to open the trigger page
4. **Wait for processing** — Podly transcribes the audio, detects ads, and removes them
5. **Listen ad-free** — Return to your podcast app and play the episode

### On-Demand Processing

Episodes are processed **only when you explicitly request it** by tapping the trigger link in the episode description. This prevents accidental processing from RSS readers or podcast app prefetching.

When you tap "Process this episode" in your podcast app:
1. A progress page opens showing processing status
2. When complete, close the tab and return to your podcast app
3. Refresh the feed and play the ad-free episode

### Authentication Modes and RSS Behavior

`REQUIRE_AUTH=true` is recommended for podcast app use.

- `REQUIRE_AUTH=true`: Podly generates tokenized RSS/feed links (`feed_token` + `feed_secret`). Podcast apps can use trigger and download links directly.
- `REQUIRE_AUTH=false`: Feed URLs are public and not tokenized. In the current release, trigger and download endpoints still rely on token/session auth, so podcast-app on-demand links may fail with auth-related errors.

If logs show `reason=not_whitelisted`, that episode is disabled for processing. Enable it in the Podcasts page first.

---

## Quick Start (Docker)

### Prerequisites
- Docker and Docker Compose
- LLM API key from [Groq](https://console.groq.com/keys) (free) or OpenAI/xAI

### 1. Clone and Configure

```bash
git clone https://github.com/lukefind/podly-unicorn.git
cd podly-unicorn
cp .env.local.example .env.local
```

Edit `.env.local`:

```bash
# Required: LLM for ad detection
LLM_API_KEY=gsk_your_groq_key
LLM_MODEL=groq/llama-3.3-70b-versatile

# Required: Whisper for transcription
WHISPER_TYPE=groq
GROQ_API_KEY=gsk_your_groq_key

# Recommended for podcast-app trigger/download links: enable authentication
REQUIRE_AUTH=true
PODLY_ADMIN_USERNAME=admin
PODLY_ADMIN_PASSWORD=your-secure-password
```

### 2. Start

```bash
docker compose up -d --build
```

### 3. Access

Open http://localhost:5001

---

## Configuration

### LLM Providers

| Provider | Model | Notes |
|----------|-------|-------|
| **Groq** | `groq/llama-3.3-70b-versatile` | Free tier, fast |
| **xAI Grok** | `xai/grok-3` | Recommended for accuracy (~$0.10/episode) |
| **OpenAI** | `gpt-4o` | High quality |

For xAI Grok:
```bash
LLM_API_KEY=xai-your-key
LLM_MODEL=xai/grok-3
OPENAI_BASE_URL=https://api.x.ai/v1
```

### Whisper (Transcription)

| Mode | Config | Notes |
|------|--------|-------|
| **Groq** | `WHISPER_TYPE=groq` | Fast, cheap, recommended |
| **Local** | `WHISPER_TYPE=local` | Free, requires RAM |

---

## Updating

```bash
cd podly-unicorn
git pull
docker compose up -d --build
```

---

## Common Commands

```bash
# View logs
docker logs -f podly-pure-podcasts

# Restart
docker compose restart

# Stop
docker compose down

# Backup database
docker cp podly-pure-podcasts:/app/src/instance/sqlite3.db ./backup.db
```

---

## Development

```bash
# Frontend (hot reload)
cd frontend && npm install && npm run dev

# Backend
docker compose up --build
```

---

## Credits

Fork of [Podly Pure Podcasts](https://github.com/jdrbc/podly_pure_podcasts) by [@jdrbc](https://github.com/jdrbc).

---

<div align="center">
  <p>
    <a href="https://github.com/lukefind/podly-unicorn">GitHub</a> •
    <a href="https://github.com/lukefind/podly-unicorn/issues">Issues</a>
  </p>
</div>
