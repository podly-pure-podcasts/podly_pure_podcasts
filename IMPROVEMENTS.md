# Recent Improvements: Customizable Prompts and Statistics

## What's New

This update adds two major features to improve ad detection and provide visibility into what's being removed:

### 1. Customizable Prompt Presets with Aggressiveness Levels

**Problem Solved**: The system was unable to catch host-read advertisements that are integrated into the podcast content.

**Solution**: Three preset aggressiveness levels that you can switch between:

- **Conservative** (0.8 confidence) - Only removes obvious ads
- **Balanced** (0.7 confidence) - Default, good for most podcasts  
- **Aggressive** (0.6 confidence) - Catches host-read ads and sponsor mentions

You can also create custom presets with your own prompts tailored to specific podcast styles.

### 2. Processing Statistics and Reports

**Problem Solved**: No visibility into how much content was removed from each episode.

**Solution**: Detailed statistics for every processed episode:

- Number of ad segments removed
- Total duration removed (e.g., "3m 45s")
- Percentage of episode removed
- Original vs processed duration
- Overall statistics across all episodes

## Quick Start

### Switch to Aggressive Mode (for host-read ads)

```bash
# List presets
curl http://localhost:5000/api/presets

# Activate aggressive preset (usually ID 3)
curl -X POST http://localhost:5000/api/presets/3/activate

# Reprocess your episodes
```

### View Your Statistics

```bash
# See overall stats
curl http://localhost:5000/api/statistics/summary

# Example output:
# {
#   "total_episodes_processed": 50,
#   "total_ad_segments_removed": 150,
#   "total_time_saved_seconds": 18000.0,
#   "total_time_saved_formatted": "5h 0m",
#   "average_percentage_removed": 10.5
# }

# See per-episode stats
curl http://localhost:5000/api/statistics/episodes
```

## Setup Instructions

### 1. Update Your Database

```bash
cd src

# Generate migration (as per project rules, you generate migrations)
python -m flask db migrate -m "Add prompt presets and processing statistics"

# Apply migration
python -m flask db upgrade

# Initialize default presets
python scripts/init_prompt_presets.py
```

### 2. Verify Setup

```bash
# Check presets are loaded
curl http://localhost:5000/api/presets

# Should show 3 presets: Conservative, Balanced, Aggressive
```

### 3. Process Episodes

New episodes will automatically use the active preset (Balanced by default) and generate statistics.

For existing episodes, reprocess them to generate statistics.

## API Endpoints

### Presets
- `GET /api/presets` - List all presets
- `GET /api/presets/<id>` - Get preset details
- `POST /api/presets/<id>/activate` - Activate a preset
- `POST /api/presets` - Create custom preset
- `PUT /api/presets/<id>` - Update preset
- `DELETE /api/presets/<id>` - Delete custom preset

### Statistics
- `GET /api/statistics/summary` - Overall statistics
- `GET /api/statistics/episodes` - Per-episode statistics (paginated)
- `GET /api/statistics/episodes/<post_id>` - Detailed episode statistics

## Files Changed/Added

### New Files
- `src/app/models.py` - Added `PromptPreset` and `ProcessingStatistics` models
- `src/prompt_presets.py` - Preset definitions
- `src/scripts/init_prompt_presets.py` - Initialization script
- `src/app/routes/preset_routes.py` - API endpoints
- `docs/PROMPT_PRESETS_AND_STATISTICS.md` - Full documentation

### Modified Files
- `src/podcast_processor/audio_processor.py` - Added statistics tracking
- `src/podcast_processor/podcast_processor.py` - Added preset support
- `src/app/routes/__init__.py` - Registered new routes

## Preset Comparison

| Preset | Min Confidence | Best For | Catches Host-Read Ads? |
|--------|---------------|----------|------------------------|
| Conservative | 0.8 | Preserving all content | No |
| Balanced | 0.7 | Most podcasts | Sometimes |
| Aggressive | 0.6 | Maximum ad removal | Yes |

## Example: Creating a Custom Preset

If the default presets don't work well for your podcast:

```bash
curl -X POST http://localhost:5000/api/presets \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Tech Podcast Preset",
    "description": "Optimized for tech podcasts with sponsor reads",
    "aggressiveness": "aggressive",
    "system_prompt": "Your custom prompt focusing on tech sponsor patterns...",
    "user_prompt_template": "This is {{podcast_title}}...",
    "min_confidence": 0.65
  }'
```

## Troubleshooting

**Q: Host-read ads still not being caught?**
- Switch to Aggressive preset
- Try creating a custom preset with more specific instructions
- Lower the min_confidence threshold

**Q: Too much content being removed?**
- Switch to Conservative preset
- Increase the min_confidence threshold
- Review the statistics to see what's being removed

**Q: Statistics not showing?**
- Ensure migrations were run
- Reprocess episodes after the update
- Check logs for errors during processing

## Next Steps

1. Run the database migrations
2. Initialize the default presets
3. Try the Aggressive preset if you're missing host-read ads
4. Check your statistics to see how much time you're saving!

For detailed documentation, see `docs/PROMPT_PRESETS_AND_STATISTICS.md`.
