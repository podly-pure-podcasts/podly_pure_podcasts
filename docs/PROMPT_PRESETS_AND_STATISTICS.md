# Prompt Presets and Statistics Feature

This document describes the new customizable prompt presets and processing statistics features added to Podly Pure Podcasts.

## Overview

The system now supports:
1. **Customizable Prompt Presets** - Different aggressiveness levels for ad detection
2. **Processing Statistics** - Detailed reporting on ad removal for each episode

## Features

### Prompt Presets

Prompt presets allow you to customize how aggressively the system detects and removes advertisements. Three default presets are provided:

#### 1. Conservative
- **Aggressiveness**: Low
- **Min Confidence**: 0.8
- **Best For**: Podcasts where you want to preserve all content except obvious sponsor reads
- **Behavior**: Only removes clear and unmistakable advertisements with explicit promotional content

#### 2. Balanced (Default)
- **Aggressiveness**: Medium
- **Min Confidence**: 0.7
- **Best For**: Most podcasts - good balance between ad removal and content preservation
- **Behavior**: Removes typical advertisements including pre-roll, mid-roll, and end-roll ads

#### 3. Aggressive
- **Aggressiveness**: High
- **Min Confidence**: 0.6
- **Best For**: Maximum ad removal, including host-read ads and sponsor mentions
- **Behavior**: Removes all promotional content including brief sponsor mentions and self-promotion
- **Note**: May occasionally remove non-ad content that sounds promotional

### Processing Statistics

For each processed episode, the system now tracks:
- **Number of ad segments removed**
- **Total duration removed** (in seconds and formatted)
- **Original episode duration**
- **Processed episode duration**
- **Percentage of content removed**
- **Which preset was used for processing**

## Setup and Migration

### 1. Run Database Migrations

After updating your code, you need to create and run database migrations to add the new tables:

```bash
# Generate migration for new models
cd src
python -m flask db migrate -m "Add prompt presets and processing statistics"

# Apply the migration
python -m flask db upgrade
```

**Important**: As per project rules, you should generate the migrations yourself rather than having them auto-created.

### 2. Initialize Default Presets

After running migrations, initialize the default prompt presets:

```bash
cd src
python scripts/init_prompt_presets.py
```

This will create the three default presets (Conservative, Balanced, Aggressive) and activate the Balanced preset by default.

## API Endpoints

### Prompt Preset Management

#### List All Presets
```
GET /api/presets
```

Response:
```json
{
  "presets": [
    {
      "id": 1,
      "name": "Conservative",
      "description": "Only removes obvious advertisements...",
      "aggressiveness": "conservative",
      "min_confidence": 0.8,
      "is_active": false,
      "is_default": true,
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T00:00:00"
    }
  ]
}
```

#### Get Preset Details
```
GET /api/presets/<preset_id>
```

Returns full preset details including system_prompt and user_prompt_template.

#### Activate a Preset
```
POST /api/presets/<preset_id>/activate
```

Activates the specified preset and deactivates all others.

#### Create Custom Preset
```
POST /api/presets
Content-Type: application/json

{
  "name": "My Custom Preset",
  "description": "Custom preset for my podcast",
  "aggressiveness": "balanced",
  "system_prompt": "Your custom system prompt...",
  "user_prompt_template": "Your custom user prompt template...",
  "min_confidence": 0.75
}
```

#### Update Preset
```
PUT /api/presets/<preset_id>
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description",
  "min_confidence": 0.8
}
```

#### Delete Custom Preset
```
DELETE /api/presets/<preset_id>
```

Note: Cannot delete default presets or the currently active preset.

### Statistics Endpoints

#### Get Summary Statistics
```
GET /api/statistics/summary
```

Response:
```json
{
  "total_episodes_processed": 150,
  "total_ad_segments_removed": 450,
  "total_time_saved_seconds": 54000.0,
  "total_time_saved_formatted": "15h 0m",
  "average_percentage_removed": 12.5
}
```

#### Get Episode Statistics (Paginated)
```
GET /api/statistics/episodes?page=1&per_page=20&feed_id=1
```

Response:
```json
{
  "episodes": [
    {
      "post_id": 1,
      "post_title": "Episode Title",
      "feed_id": 1,
      "release_date": "2024-01-01T00:00:00",
      "statistics": {
        "segments_removed": 3,
        "duration_removed_seconds": 180.5,
        "duration_removed_formatted": "3m 0s",
        "original_duration_seconds": 3600.0,
        "processed_duration_seconds": 3419.5,
        "percentage_removed": 5.01,
        "processed_at": "2024-01-01T12:00:00"
      }
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "pages": 8,
    "has_next": true,
    "has_prev": false
  }
}
```

#### Get Detailed Episode Statistics
```
GET /api/statistics/episodes/<post_id>
```

Returns detailed statistics for a specific episode including which preset was used.

## Usage Examples

### Switching to Aggressive Mode

If you find that host-read ads are not being caught:

1. List available presets:
   ```bash
   curl -X GET http://localhost:5000/api/presets
   ```

2. Activate the Aggressive preset:
   ```bash
   curl -X POST http://localhost:5000/api/presets/3/activate
   ```

3. Reprocess episodes to apply the new preset

### Viewing Statistics

Check how much time you've saved:

```bash
curl -X GET http://localhost:5000/api/statistics/summary
```

View statistics for a specific feed:

```bash
curl -X GET "http://localhost:5000/api/statistics/episodes?feed_id=1&per_page=50"
```

## Custom Presets

You can create custom presets with your own prompts. This is useful if:
- The default presets don't work well for your specific podcasts
- You want to fine-tune the detection for a particular podcast style
- You want to experiment with different prompt strategies

### Creating a Custom Preset

```bash
curl -X POST http://localhost:5000/api/presets \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Podcast Preset",
    "description": "Optimized for tech podcasts",
    "aggressiveness": "balanced",
    "system_prompt": "Your custom system prompt here...",
    "user_prompt_template": "This is the podcast {{podcast_title}}...",
    "min_confidence": 0.75
  }'
```

### Prompt Template Variables

User prompt templates support Jinja2 templating with these variables:
- `{{podcast_title}}` - The podcast title
- `{{podcast_topic}}` - The podcast topic/description
- `{{transcript}}` - The transcript excerpt

## Technical Details

### Database Schema

#### `prompt_preset` Table
- `id`: Primary key
- `name`: Unique preset name
- `description`: Description of the preset
- `aggressiveness`: conservative|balanced|aggressive
- `system_prompt`: LLM system prompt
- `user_prompt_template`: Jinja2 template for user prompt
- `min_confidence`: Minimum confidence threshold (0.0-1.0)
- `is_active`: Whether this preset is currently active
- `is_default`: Whether this is a default preset
- `created_at`, `updated_at`: Timestamps

#### `processing_statistics` Table
- `id`: Primary key
- `post_id`: Foreign key to post (unique)
- `total_ad_segments_removed`: Count of ad segments removed
- `total_duration_removed_seconds`: Total time removed
- `original_duration_seconds`: Original episode duration
- `processed_duration_seconds`: Duration after ad removal
- `percentage_removed`: Percentage of content removed
- `prompt_preset_id`: Foreign key to preset used (nullable)
- `created_at`, `updated_at`: Timestamps

### How It Works

1. **During Processing**: The system checks for an active preset
   - If found, uses the preset's prompts and confidence threshold
   - If not found, falls back to default prompt files

2. **After Audio Processing**: Statistics are calculated and stored
   - Counts merged ad segments
   - Calculates total duration removed
   - Stores which preset was used

3. **Statistics Persistence**: Statistics are stored per episode
   - Allows historical tracking
   - Enables comparison between different presets
   - Supports aggregate reporting

## Troubleshooting

### Preset Not Being Used

If your active preset doesn't seem to be working:

1. Verify a preset is active:
   ```bash
   curl -X GET http://localhost:5000/api/presets | jq '.presets[] | select(.is_active==true)'
   ```

2. Check the logs during processing - should see:
   ```
   Using active prompt preset: Aggressive (aggressiveness: aggressive)
   ```

### Statistics Not Showing

If statistics aren't being recorded:

1. Ensure migrations have been run
2. Check that episodes were processed after the update
3. Reprocess an episode to generate statistics

### Host-Read Ads Still Not Caught

Try these steps:
1. Switch to the Aggressive preset
2. Lower the min_confidence threshold in your preset
3. Create a custom preset with more specific instructions for your podcast type

## Future Enhancements

Potential improvements for future versions:
- Per-feed preset configuration
- A/B testing between presets
- Machine learning to auto-tune presets based on user feedback
- Visual statistics dashboard in the frontend
- Export statistics to CSV/JSON
- Preset sharing and community presets
