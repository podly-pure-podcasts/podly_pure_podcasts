import contextlib
import json
import logging
import logging.handlers
import os
import weakref
from collections.abc import Iterator
from typing import TextIO

from app.sanitize import redact_secrets
from shared import defaults as DEFAULTS

_MB = 1024 * 1024
# Current rotation settings; changed by configure_log_rotation() once the app
# settings are loaded, and on every settings save.
_rotation_max_mb = DEFAULTS.APP_LOG_MAX_MB
_rotation_backup_count = DEFAULTS.APP_LOG_BACKUP_COUNT
_rotating_handlers: "weakref.WeakSet[MultiProcessRotatingFileHandler]" = (
    weakref.WeakSet()
)


class ExtraFormatter(logging.Formatter):
    """Formatter that appends structured extras to log lines.

    Any LogRecord attributes not in the standard set are captured into a JSON
    object and appended as ``extra={...}`` so contextual fields are visible in
    plain-text logs.
    """

    _standard_attrs = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "asctime",
    }

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v for k, v in record.__dict__.items() if k not in self._standard_attrs
        }
        if extras:
            try:
                extras_json = json.dumps(extras, ensure_ascii=True, default=str)
            except Exception:  # noqa: BLE001
                extras_json = str(extras)
            final_str = f"{base} | extra={extras_json}"
        else:
            final_str = base

        return redact_secrets(final_str)


def configure_log_rotation(max_mb: int, backup_count: int) -> None:
    """Apply the app's log settings to every log file handler in this process.

    ``max_mb`` of 0 turns rotation off. At least one old file is kept: with
    none, ``RotatingFileHandler`` never rotates and reopens the file for every
    record once it is over the limit. Called when the runtime config is
    hydrated, so the web app and the writer service both pick up a change made
    on the Config page.
    """
    global _rotation_max_mb, _rotation_backup_count
    _rotation_max_mb = max(0, int(max_mb))
    _rotation_backup_count = max(1, int(backup_count))
    for handler in list(_rotating_handlers):
        handler.acquire()
        try:
            handler.maxBytes = _rotation_max_mb * _MB
            handler.backupCount = _rotation_backup_count
        finally:
            handler.release()


class MultiProcessRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Size-based rotation for a log file that several processes append to.

    The web app and the writer service both write ``app.log``. When one of them
    rotates the file, the other still holds the renamed file open: a plain
    ``RotatingFileHandler`` keeps writing there and soon rotates it again, and
    two rollovers at once delete the file the first one just made.
    Before each record this handler reopens the path if it now names a
    different file, and a rollover runs under a lock and only if no other
    process has rotated the file in the meantime.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._reopen_if_moved()
        except Exception:  # noqa: BLE001
            self.handleError(record)
            return
        super().emit(record)

    def doRollover(self) -> None:
        with self._rollover_lock():
            if self._reopen_if_moved():
                return
            super().doRollover()

    def _reopen_if_moved(self) -> bool:
        stream = self.stream
        if stream is None or not self._path_moved(stream):
            return False
        stream.close()
        self.stream = self._open()
        return True

    @contextlib.contextmanager
    def _rollover_lock(self) -> Iterator[None]:
        try:
            import fcntl
        except ImportError:  # no fcntl on Windows: rotate without the lock
            yield
            return
        with open(self.baseFilename + ".lock", "a") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    def _path_moved(self, stream: TextIO) -> bool:
        try:
            on_disk = os.stat(self.baseFilename)
            current = os.fstat(stream.fileno())
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return (on_disk.st_dev, on_disk.st_ino) != (current.st_dev, current.st_ino)


def setup_logger(
    name: str, log_file: str, level: int = logging.DEBUG
) -> logging.Logger:
    """Create or return a configured logger.

    - Writes to the specified log_file, rotated per configure_log_rotation()
    - Emits to console exactly once (no duplicates)
    - Disables propagation to avoid duplicate root handling
    - Guards against adding duplicate handlers across repeated calls
    """
    file_formatter = ExtraFormatter("%(asctime)s %(levelname)s %(message)s")
    console_formatter = ExtraFormatter("%(levelname)s  [%(name)s] %(message)s")

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Prevent records from also bubbling up to root logger handlers (which can cause duplicates)
    logger.propagate = False

    # Ensure directory exists for log file
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Add file handler if not already present for this file
    abs_log_file = os.path.abspath(log_file)
    has_file_handler = any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", None) == abs_log_file
        for h in logger.handlers
    )
    if not has_file_handler:
        file_handler = MultiProcessRotatingFileHandler(
            abs_log_file,
            maxBytes=_rotation_max_mb * _MB,
            backupCount=_rotation_backup_count,
        )
        _rotating_handlers.add(file_handler)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    # Add a single console handler if not already present
    has_stream_handler = any(
        isinstance(h, logging.StreamHandler) for h in logger.handlers
    )
    if not has_stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(console_formatter)
        logger.addHandler(stream_handler)

    return logger
