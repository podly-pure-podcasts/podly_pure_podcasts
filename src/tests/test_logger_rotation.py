import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from app.config_store import (
    _update_section_app,
    hydrate_runtime_config_inplace,
    read_combined,
    to_pydantic_config,
)
from app.extensions import db
from app.logger import (
    MultiProcessRotatingFileHandler,
    configure_log_rotation,
    setup_logger,
)
from app.models import AppSettings
from shared import defaults as DEFAULTS

from .test_env_var_authority import _create_default_settings

MB = 1024 * 1024
LINE = "x" * 1000


@pytest.fixture(autouse=True)
def _restore_default_rotation() -> Generator[None, None, None]:
    yield
    configure_log_rotation(DEFAULTS.APP_LOG_MAX_MB, DEFAULTS.APP_LOG_BACKUP_COUNT)


@pytest.fixture
def make_logger() -> Generator:
    names: list[str] = []

    def _make(name: str, log_file: Path) -> logging.Logger:
        names.append(name)
        return setup_logger(name, str(log_file))

    yield _make

    for name in names:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


def _file_handler(logger: logging.Logger) -> MultiProcessRotatingFileHandler:
    handlers = [
        h for h in logger.handlers if isinstance(h, MultiProcessRotatingFileHandler)
    ]
    assert len(handlers) == 1
    return handlers[0]


def test_rotates_at_configured_size(tmp_path: Path, make_logger) -> None:
    configure_log_rotation(1, 2)
    log_file = tmp_path / "app.log"
    logger = make_logger("test_logger_rotation", log_file)

    for _ in range(3500):
        logger.info(LINE)

    assert log_file.exists()
    assert (tmp_path / "app.log.1").exists()
    assert (tmp_path / "app.log.2").exists()
    assert not (tmp_path / "app.log.3").exists()
    for path in tmp_path.glob("app.log*"):
        assert path.stat().st_size <= MB


def test_second_handler_follows_rotation_by_first(tmp_path: Path, make_logger) -> None:
    """Two handlers on one file stand in for the web and writer processes."""
    configure_log_rotation(1, 3)
    log_file = tmp_path / "app.log"
    web = make_logger("test_logger_web", log_file)
    writer = make_logger("test_logger_writer", log_file)

    while not (tmp_path / "app.log.1").exists():
        web.info(LINE)
    writer.info("after-rotation marker")

    assert "after-rotation marker" in log_file.read_text()
    assert "after-rotation marker" not in (tmp_path / "app.log.1").read_text()
    assert not (tmp_path / "app.log.2").exists()


def test_rollover_skipped_when_other_handler_rotated_first(
    tmp_path: Path, make_logger
) -> None:
    """Both processes reach the size limit together: only one rotation happens."""
    configure_log_rotation(1, 3)
    log_file = tmp_path / "app.log"
    web = make_logger("test_logger_race_web", log_file)
    writer = make_logger("test_logger_race_writer", log_file)
    web.info("before rotation")

    _file_handler(web).doRollover()
    _file_handler(writer).doRollover()
    writer.info("after-rotation marker")

    assert "before rotation" in (tmp_path / "app.log.1").read_text()
    assert not (tmp_path / "app.log.2").exists()
    assert "after-rotation marker" in log_file.read_text()


def test_recreates_file_removed_by_something_else(tmp_path: Path, make_logger) -> None:
    log_file = tmp_path / "app.log"
    logger = make_logger("test_logger_removed", log_file)
    logger.info("before")
    log_file.unlink()

    logger.info("after")

    assert log_file.read_text().strip().endswith("after")


def test_configure_updates_existing_handlers(tmp_path: Path, make_logger) -> None:
    handler = _file_handler(make_logger("test_logger_configure", tmp_path / "app.log"))
    assert handler.maxBytes == DEFAULTS.APP_LOG_MAX_MB * MB
    assert handler.backupCount == DEFAULTS.APP_LOG_BACKUP_COUNT

    configure_log_rotation(3, 2)
    assert (handler.maxBytes, handler.backupCount) == (3 * MB, 2)

    # 0 MB turns rotation off; at least one old file is always kept.
    configure_log_rotation(0, 0)
    assert (handler.maxBytes, handler.backupCount) == (0, 1)


def test_saved_app_settings_apply_to_log_handlers(
    app: Any, tmp_path: Path, make_logger
) -> None:
    handler = _file_handler(make_logger("test_logger_settings", tmp_path / "app.log"))

    with app.app_context():
        _create_default_settings()
        assert read_combined()["app"]["log_max_mb"] == DEFAULTS.APP_LOG_MAX_MB
        assert (
            read_combined()["app"]["log_backup_count"] == DEFAULTS.APP_LOG_BACKUP_COUNT
        )

        _update_section_app({"log_max_mb": 3, "log_backup_count": 2})
        hydrate_runtime_config_inplace()

        assert read_combined()["app"]["log_max_mb"] == 3
        assert (handler.maxBytes, handler.backupCount) == (3 * MB, 2)


def test_out_of_range_stored_settings_are_clamped(app: Any) -> None:
    with app.app_context():
        _create_default_settings()
        row = db.session.get(AppSettings, 1)
        assert row is not None
        row.log_max_mb = -5
        row.log_backup_count = 0
        db.session.commit()

        cfg = to_pydantic_config()

    assert (cfg.log_max_mb, cfg.log_backup_count) == (0, 1)


@pytest.mark.parametrize(
    ("sent", "stored"),
    [
        ({"log_max_mb": None, "log_backup_count": None}, (10, 5)),
        ({"log_max_mb": "", "log_backup_count": "abc"}, (10, 5)),
        ({"log_max_mb": -2, "log_backup_count": 0}, (0, 1)),
        ({"log_max_mb": "25", "log_backup_count": 3}, (25, 3)),
    ],
)
def test_saving_empty_or_invalid_log_settings_stores_valid_values(
    app: Any, sent: dict[str, Any], stored: tuple[int, int]
) -> None:
    """A cleared Config page field arrives as null and must not reach the DB."""
    with app.app_context():
        _create_default_settings()

        _update_section_app(sent)

        app_cfg = read_combined()["app"]
        assert (app_cfg["log_max_mb"], app_cfg["log_backup_count"]) == stored
