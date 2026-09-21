from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def test_migrations_have_single_head() -> None:
    # Startup runs `flask db upgrade` (target "head"), which aborts when the
    # revision graph has more than one head. Add a merge revision if this fails.
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"Multiple alembic heads: {heads}"
