# Reintegration Plan: podly-unicorn → podly_pure_podcasts (upstream main)

## Overview

This PR brings 559+ commits of improvements from the `podly-unicorn` fork back into the upstream `podly_pure_podcasts` repo. The fork introduced a comprehensive React frontend, multi-theme support, enhanced LLM/Whisper configuration, user management, preset system, and many UX improvements.

**Key decision**: The new blue theme (`original`) becomes the **default** theme. The unicorn (light/dark) themes remain as switchable alternatives.

---

## Checklist

### 1. Branding & Naming
- [x] Rename all "Podly Unicorn" references → "Podly" in UI text, meta tags, manifest
- [x] `index.html`: title, og:title, twitter:title, apple-mobile-web-app-title → "Podly"
- [x] `manifest.json`: name → "Podly"
- [x] `theme.ts`: brand name for all themes → "Podly" (no more "Podly Unicorn")
- [x] `TriggerPage.tsx`: all 4 header instances → "Podly"
- [x] `OnboardingModal.tsx`: welcome text → "Podly"
- [x] `HelpModal.tsx`: welcome text → "Podly"

### 2. Community Links (Telegram → Discord)
- [x] `Sidebar.tsx`: Telegram link + icon → Discord link + icon
- [x] `ConfigPage.tsx`: Telegram badge → Discord badge
- [x] `HomePage.tsx`: Telegram badge → Discord badge
- [x] `README.md`: Telegram badge → Discord badge
- [x] `STATUS.md`: Telegram → Discord
- [x] `docs/how_to_run_beginners.md`: Telegram → Discord

### 3. GitHub Repository Links
- [x] `README.md`: lukefind/podly-unicorn → podly-pure-podcasts/podly_pure_podcasts
- [x] `STATUS.md`: same
- [x] `docs/how_to_run_beginners.md`: same
- [x] `LoginPage.tsx`: GitHub link → upstream repo
- [x] `HelpModal.tsx`: issues link → upstream repo

### 4. Default Theme → Blue ("original")
- [x] `ThemeContext.tsx`: new users default to 'original' instead of system preference
- [x] Theme switcher labels: rename "Original" → "Blue", keep light/dark as-is
- [x] Existing users who have a stored theme preference are unaffected (localStorage)

### 5. Logos & Favicons
- [x] Primary favicon/logo: use the new blue-theme Podly logo (`original-logo.png`) as the default
- [x] `theme.ts`: all themes use `original-logo.png` as primary, unicorn logo only for light/dark
- [x] `manifest.json`: primary icon → blue-theme logo
- [x] `index.html`: favicon references stay as-is (already use generic favicon.svg)
- [ ] **Manual step**: Generate new favicon-96x96.png, apple-touch-icon.png, web-app-manifest PNGs from the blue-theme logo (requires image tooling — flag for contributor)

### 6. Trigger Page Theming
- [x] Apply blue theme styling to all trigger page states (missing params, error, ready, processing)
- [x] Replace purple gradients with blue gradients matching the app's blue theme
- [x] Update header branding to "Podly"

### 7. Database Migration Safety
- [x] Audit all 33 migration files — confirm all are **additive** (new tables, new columns, new indexes)
- [x] No destructive migrations (no DROP TABLE, no DROP COLUMN, no column renames on existing data)
- [x] Existing users upgrading from upstream will have Alembic auto-apply new migrations on startup
- [x] The `docker-entrypoint.sh` already runs `flask db upgrade` on startup

### 8. Documentation Updates
- [x] `README.md`: update for upstream context, remove fork-specific references
- [x] `AGENTS.md`: update repo references
- [x] `docs/how_to_run_beginners.md`: update clone URLs and links
- [x] `STATUS.md`: update support links
- [x] `CHANGELOG_UNICORN.md`: keep as historical reference, no changes needed

### 9. CSS/Theme Integrity
- [x] `unicorn-card` CSS class: keep as-is (used by light/dark themes, harmless in blue)
- [x] `rainbow-text` CSS class: keep as-is (used by light/dark themes)
- [x] Blue theme overrides via `[data-theme="original"]` selectors: keep as-is
- [x] No CSS changes needed — all themes remain functional

---

## Database Safety Analysis

All migrations in `src/migrations/versions/` are **additive**:
- New tables: `user`, `user_feed_subscription`, `user_download`, `prompt_preset`, `processing_job`, `llm_key_profile`, `feed_access_token`, `config_*` tables, `transcript_segment`
- New columns: `image_url`, `download_count`, `is_hidden`, `default_prompt_preset_id`, `processed_with_preset_id`, etc.
- New indexes on existing columns
- No destructive operations

**Risk**: Zero. Existing databases will gain new tables/columns. No data loss.

---

## Theme Architecture

After reintegration:
- **Blue** (default): Deep blue gradient, professional look. Internal name: `original`
- **Light**: Pastel unicorn theme with rainbow accents. Internal name: `light`
- **Dark**: Dark purple unicorn theme. Internal name: `dark`

The theme switcher in the sidebar shows: `Light | Dark | Blue`

Existing users who stored a theme preference keep their choice. New users get Blue.
