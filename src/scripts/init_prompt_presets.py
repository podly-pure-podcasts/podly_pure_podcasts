"""
Initialize default prompt presets in the database.
This script should be run after database migrations to populate the prompt_preset table.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from flask import Flask
from app.extensions import db
from app.models import PromptPreset
from prompt_presets import PRESET_DEFINITIONS


def init_prompt_presets(app: Flask) -> None:
    """Initialize prompt presets in the database."""
    with app.app_context():
        print("Initializing prompt presets...")
        
        for preset_def in PRESET_DEFINITIONS:
            # Check if preset already exists
            existing = PromptPreset.query.filter_by(name=preset_def["name"]).first()
            
            if existing:
                print(f"  Preset '{preset_def['name']}' already exists, updating...")
                existing.description = preset_def["description"]
                existing.aggressiveness = preset_def["aggressiveness"]
                existing.system_prompt = preset_def["system_prompt"]
                existing.user_prompt_template = preset_def["user_prompt_template"]
                existing.min_confidence = preset_def["min_confidence"]
                existing.is_default = preset_def["is_default"]
            else:
                print(f"  Creating preset '{preset_def['name']}'...")
                preset = PromptPreset(
                    name=preset_def["name"],
                    description=preset_def["description"],
                    aggressiveness=preset_def["aggressiveness"],
                    system_prompt=preset_def["system_prompt"],
                    user_prompt_template=preset_def["user_prompt_template"],
                    min_confidence=preset_def["min_confidence"],
                    is_active=preset_def["is_default"],  # Activate default preset
                    is_default=preset_def["is_default"],
                )
                db.session.add(preset)
        
        db.session.commit()
        print("Prompt presets initialized successfully!")
        
        # Display all presets
        presets = PromptPreset.query.all()
        print("\nAvailable presets:")
        for preset in presets:
            status = "ACTIVE" if preset.is_active else "inactive"
            default = " (DEFAULT)" if preset.is_default else ""
            print(f"  - {preset.name} [{preset.aggressiveness}] - {status}{default}")


if __name__ == "__main__":
    # Create minimal Flask app for database access
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///instance/podly.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    db.init_app(app)
    init_prompt_presets(app)
