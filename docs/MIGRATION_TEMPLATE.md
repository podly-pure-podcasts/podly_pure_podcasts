# Migration Template for Prompt Presets and Statistics

This file provides a reference for the database schema changes needed. You should generate the actual migration using Flask-Migrate.

## Required Changes

### New Tables

#### 1. prompt_preset

```sql
CREATE TABLE prompt_preset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    aggressiveness VARCHAR(20) NOT NULL DEFAULT 'balanced',
    system_prompt TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,
    min_confidence FLOAT NOT NULL DEFAULT 0.7,
    is_active BOOLEAN NOT NULL DEFAULT 0,
    is_default BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. processing_statistics

```sql
CREATE TABLE processing_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL UNIQUE,
    total_ad_segments_removed INTEGER NOT NULL DEFAULT 0,
    total_duration_removed_seconds FLOAT NOT NULL DEFAULT 0.0,
    original_duration_seconds FLOAT NOT NULL,
    processed_duration_seconds FLOAT NOT NULL,
    percentage_removed FLOAT NOT NULL DEFAULT 0.0,
    prompt_preset_id INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES post(id),
    FOREIGN KEY (prompt_preset_id) REFERENCES prompt_preset(id)
);
```

## Steps to Apply

1. **Generate Migration**
   ```bash
   cd src
   python -m flask db migrate -m "Add prompt presets and processing statistics"
   ```

2. **Review Generated Migration**
   - Check the generated migration file in `migrations/versions/`
   - Ensure it includes both new tables
   - Verify foreign key constraints are correct

3. **Apply Migration**
   ```bash
   python -m flask db upgrade
   ```

4. **Initialize Default Presets**
   ```bash
   python scripts/init_prompt_presets.py
   ```

5. **Verify**
   ```bash
   # Check tables exist
   python -c "
   from app import create_app
   from app.models import PromptPreset, ProcessingStatistics
   app = create_app()
   with app.app_context():
       print('Presets:', PromptPreset.query.count())
       print('Statistics:', ProcessingStatistics.query.count())
   "
   ```

## Rollback (if needed)

If you need to rollback:

```bash
cd src
python -m flask db downgrade
```

This will remove the new tables and restore the previous schema.
