# Podly Unicorn - Changelog

**Fork of:** [jdrbc/podly_pure_podcasts](https://github.com/jdrbc/podly_pure_podcasts)

---

## [1.1.0] - December 11, 2024

### ✨ New Features

#### Feed Subscription System
- **Per-user feed filtering** - Users only see feeds they've subscribed to on the Podcasts page
- **"Browse Podcasts on Server"** button - Users can discover and subscribe to feeds added by others
- **Private subscriptions** - Users can subscribe privately so their subscription isn't visible to other users
- **Admin Subscriptions page** (`/subscriptions`) - Admins can view all feeds with subscriber lists and usage stats
- **Inline subscription controls** - Each feed shows Public/Private toggle and Unsubscribe button

#### Privacy Controls
- **Public vs Private subscriptions** - Split subscribe button with eye icon for private option
- **Feed visibility rules** - Feeds only appear in browse if at least one user has a public subscription
- **Private indicator** - Admin page shows private subscriptions with eye-slash icon (grayed out)

#### Improved Delete Behavior
- **Smart deletion** - Clicking delete unsubscribes the user; feed is only fully deleted if no other subscribers remain
- **Safe for shared feeds** - Users can't accidentally delete feeds others are using

#### On-Demand Processing
- **Episodes enabled but not auto-processed** - Enabling an episode marks it as eligible, but doesn't start processing
- **Process button** - New purple "Process" button for enabled episodes that haven't been processed yet
- **Reprocess button** - Orange "Reprocess" button only shows for already-processed episodes
- **Processing triggered by**: Manual "Process" click or podcast app RSS request

#### Improved Episode Status UI
- **Enabled** (blue) - Episode is eligible for processing
- **Disabled** (gray dashed) - Episode is skipped entirely
- **Ready** (green) - Episode has been processed and is ready to play
- **"How processing works"** help modal - Explains the workflow in detail

### 🔧 Technical Changes

#### New Database Model
- `UserFeedSubscription` table with fields: `user_id`, `feed_id`, `subscribed_at`, `is_private`

#### New API Endpoints
- `POST /api/feeds/<id>/subscribe` - Subscribe to a feed (with optional `private` flag)
- `POST /api/feeds/<id>/unsubscribe` - Unsubscribe from a feed
- `GET /api/feeds/all` - Get all discoverable feeds for subscription modal
- `GET /api/admin/feed-subscriptions` - Admin endpoint for subscription overview

#### Processing Changes
- Removed auto-job creation when enabling episodes
- Jobs only created on-demand via UI or RSS request
- Default cleanup retention changed from 5 to 14 days

#### Performance Optimizations
- Optimized `/feeds` endpoint with efficient `COUNT()` query instead of lazy loading
- Fixed N+1 query issue that was causing slow page loads

### 📁 Files Changed

| File | Changes |
|------|---------|
| `src/app/models.py` | Added `UserFeedSubscription` model |
| `src/app/routes/feed_routes.py` | Added subscription endpoints, optimized queries, smart delete logic |
| `src/app/feeds.py` | Removed auto-job creation on feed add/refresh |
| `src/app/jobs_manager.py` | Disabled auto-job creation for whitelisted posts |
| `src/shared/defaults.py` | Changed cleanup retention to 14 days |
| `frontend/src/pages/PodcastsPage.tsx` | Subscription controls, Process button, help modal |
| `frontend/src/pages/SubscriptionsPage.tsx` | New admin subscriptions page |
| `frontend/src/components/ProcessButton.tsx` | New component for processing unprocessed episodes |
| `frontend/src/services/api.ts` | Added subscription API methods |
| `AGENTS.md` | Added Feed Subscriptions documentation |

### 🐛 Bug Fixes
- Fixed feed delete failing due to SQLAlchemy cascade issues (now uses raw SQL)
- Fixed slow Podcasts page load due to N+1 query on posts count
- Fixed episodes not showing correct status when subscribing to existing feeds

---

## [1.0.0-unicorn] - December 10, 2024

---

## 🦄 Overview

Podly Unicorn is a themed fork of Podly with a beautiful pastel UI, optimized LLM prompts for ad detection, improved UX, and comprehensive documentation.

---

## ✨ New Features & Improvements

### 🎨 UI/UX - Pastel Unicorn Theme

Complete visual overhaul with a cohesive pastel color scheme:

- **Global Theme**
  - Blue-dominant pastel gradient background
  - Purple-tinted text colors replacing grays
  - Semi-transparent white backgrounds with backdrop blur
  - Rounded corners (`rounded-xl`) on all interactive elements

- **Sidebar** (`frontend/src/components/layout/Sidebar.tsx`)
  - Gradient background (pink → purple → cyan)
  - Rainbow shimmer animation on "Podly Unicorn" title
  - Improved collapse button visibility with purple background

- **Dashboard** (`frontend/src/pages/DashboardPage.tsx`)
  - Gradient stat cards with unicorn theme
  - Purple-tinted text and borders

- **Jobs Page** (`frontend/src/pages/JobsPage.tsx`)
  - Themed job cards and filter buttons
  - Gradient action buttons

- **Settings Page** (`frontend/src/pages/ConfigPage.tsx`)
  - Themed section headers
  - Improved form styling

- **Podcasts Page** (`frontend/src/pages/PodcastsPage.tsx`)
  - Redesigned episode cards with hover effects
  - New action buttons with clear labels and icons:
    - **Skip/Enable** - Toggle episode processing eligibility
    - **Play** - Gradient play button
    - **Download** - Teal gradient with download icon
    - **Process** - Purple themed with spinner
    - **Reprocess** - Orange themed with refresh icon
    - **Stats** - Purple themed with chart icon
  - Added **Subscribe to Podly RSS** button
  - Added **Refresh Feed** button
  - Added **Original RSS** link
  - Added **More Options menu** (⋮) with:
    - Enable all episodes
    - Disable all episodes
    - Explain enable/disable
    - Delete feed
  - Podcast description now displayed

- **Modals** (`ProcessingStatsButton.tsx`, `ReprocessButton.tsx`)
  - Fixed z-index issues using `createPortal` to render to `document.body`
  - Purple backdrop with blur effect
  - Solid white backgrounds for readability
  - Proper text contrast with inline styles

### 📝 Optimized LLM Prompts

Completely rewritten prompt presets for better ad detection (`src/prompt_presets.py`):

| Preset | Changes |
|--------|---------|
| **Conservative** | Clear structure with explicit examples of what IS and IS NOT an ad. Focus on unmistakable sponsor reads only. |
| **Balanced** | Comprehensive guidelines for typical podcast ads. Better handling of host-read ads vs organic discussion. |
| **Aggressive** | Expanded to catch self-promotion, Patreon pitches, subscribe requests. Clear confidence scoring guidance. |
| **Maximum** | Nuclear option with instructions to flag anything remotely promotional. Explicit warning about false positives. |

All prompts now include:
- Structured sections (What IS an ad, What is NOT, Key principles)
- JSON output format specification
- Confidence score guidelines
- Concrete examples

### 📚 Documentation

- **`README.md`** - Updated with:
  - "Podly Unicorn" branding
  - Fork attribution and link to original
  - Clarified on-demand processing flow
  - Updated "How It Works" section

- **`docs/ARCHITECTURE.md`** (New) - Comprehensive architecture guide:
  - Directory structure
  - Database schema and locations
  - Prompt preset system
  - Processing flow diagram
  - API routes reference
  - LLM configuration details
  - Frontend theme documentation
  - Docker commands

- **`AGENTS.md`** - Expanded AI assistant guidelines:
  - Database location (correct Docker path)
  - Preset update script (copy-paste ready)
  - Frontend theme notes
  - Modal rendering tips
  - CSS override patterns

### 🔧 Technical Improvements

- **CSS Architecture** (`frontend/src/index.css`)
  - Custom CSS variables for unicorn colors
  - Global overrides for gray → purple tints
  - `.modal-content` class to reset colors inside modals
  - `.unicorn-card` hover effects
  - `.rainbow-text` animation

- **Tailwind Config** (`frontend/tailwind.config.js`)
  - Extended color palette with pastel unicorn colors

---

## 📁 Files Changed

### Frontend

| File | Changes |
|------|---------|
| `frontend/src/index.css` | Added unicorn theme CSS, color overrides, animations |
| `frontend/tailwind.config.js` | Added custom pastel color palette |
| `frontend/src/components/layout/Sidebar.tsx` | Gradient background, rainbow title, improved collapse button |
| `frontend/src/components/PlayButton.tsx` | Gradient styling, rounded corners |
| `frontend/src/components/DownloadButton.tsx` | Themed buttons with icons, gradient progress bar |
| `frontend/src/components/ReprocessButton.tsx` | Orange theme, createPortal for modal, icons |
| `frontend/src/components/ProcessingStatsButton.tsx` | createPortal for modal, themed tabs and cards, proper contrast |
| `frontend/src/pages/DashboardPage.tsx` | Unicorn theme applied to all cards and stats |
| `frontend/src/pages/JobsPage.tsx` | Themed job cards and buttons |
| `frontend/src/pages/ConfigPage.tsx` | Themed section headers |
| `frontend/src/pages/PodcastsPage.tsx` | Complete redesign: episode cards, action buttons, RSS buttons, dropdown menu, description |

### Backend

| File | Changes |
|------|---------|
| `src/prompt_presets.py` | Completely rewritten all 4 preset prompts and descriptions |

### Documentation

| File | Changes |
|------|---------|
| `README.md` | Rebranded to Podly Unicorn, added fork attribution, clarified on-demand processing |
| `AGENTS.md` | Expanded with comprehensive AI assistant guidelines |
| `docs/ARCHITECTURE.md` | New comprehensive architecture documentation |
| `CHANGELOG_UNICORN.md` | This file |

---

## 🐛 Bug Fixes

- **Modal z-index issues** - Modals now render via `createPortal` to `document.body`, preventing them from being clipped by parent containers
- **Text contrast in modals** - Added inline styles to override global CSS overrides inside modals
- **Collapse button visibility** - Added background and border to sidebar collapse button when minimized
- **Episode action buttons** - Replaced confusing checkmark icon with clear "Skip"/"Enable" text labels
- **Preset confidence sync** - Activating a preset now automatically updates Output Settings `min_confidence` to match
- **ffmpeg audio processing** - Added fallback for when complex filter fails with many ad segments
- **Toast notifications** - Styled with unicorn theme (gradient background, purple icons)

---

## 💡 UX Clarifications

- **On-demand processing** - Added clear explanation in UI and README that episodes are NOT auto-processed when enabled. Processing only occurs when:
  1. Podcast app requests the episode from Podly RSS
  2. User manually clicks "Process"

- **Enable/Disable terminology** - Replaced "whitelist" with clearer "Enable"/"Skip" language

---

## 🔄 Migration Notes

### For existing Podly users upgrading to Unicorn:

1. **Prompt presets need database update** - The new prompts are in code but must be synced to the database:

```bash
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

2. **User-created presets are preserved** - The update script only modifies the 4 default presets.

3. **Reprocess episodes** - To use new prompts on existing episodes, use the "Reprocess" button.

---

## 🙏 Credits

- **Original Podly** - [jdrbc/podly_pure_podcasts](https://github.com/jdrbc/podly_pure_podcasts)
- **Unicorn Theme & Improvements** - This fork

---

## 📋 Commit Summary

```
feat: Podly Unicorn - pastel theme, optimized prompts, improved UX

- Complete UI overhaul with pastel unicorn theme
- Rewritten LLM prompts for all 4 aggressiveness presets
- Fixed modal z-index issues with createPortal
- Added Subscribe to RSS, Refresh Feed, and dropdown menu
- Replaced whitelist checkmark with clear Skip/Enable buttons
- Added comprehensive documentation (ARCHITECTURE.md, AGENTS.md)
- Clarified on-demand processing in UI and README
```
