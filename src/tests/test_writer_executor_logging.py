import logging
from collections.abc import Generator
from typing import Any

import pytest

from app.writer.executor import CommandExecutor
from app.writer.protocol import WriteCommand, WriteCommandType


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def writer_records() -> Generator[_ListHandler, None, None]:
    # The writer logger may not propagate to the root logger, so capture it directly.
    writer_logger = logging.getLogger("writer")
    handler = _ListHandler()
    old_level = writer_logger.level
    writer_logger.addHandler(handler)
    writer_logger.setLevel(logging.DEBUG)
    yield handler
    writer_logger.removeHandler(handler)
    writer_logger.setLevel(old_level)


def _processing_lines(handler: _ListHandler) -> list[tuple[int, str]]:
    return [
        (r.levelno, r.getMessage())
        for r in handler.records
        if r.getMessage().startswith("[WRITER] Processing command")
    ]


def _action(action: str, cmd_id: str) -> WriteCommand:
    return WriteCommand(
        id=cmd_id,
        type=WriteCommandType.ACTION,
        model=None,
        data={"action": action, "params": {}},
    )


@pytest.mark.parametrize("dequeued", [None, {"job_id": "job-1"}])
def test_dequeue_job_poll_is_logged_at_debug(
    app: Any, writer_records: _ListHandler, dequeued: dict[str, str] | None
) -> None:
    executor = CommandExecutor(app)
    executor.register_action("dequeue_job", lambda _params: dequeued)

    result = executor.process_command(_action("dequeue_job", "poll-1"))

    assert result.success
    lines = _processing_lines(writer_records)
    assert len(lines) == 1
    assert lines[0][0] == logging.DEBUG


def test_other_actions_are_still_logged_at_info(
    app: Any, writer_records: _ListHandler
) -> None:
    executor = CommandExecutor(app)
    executor.register_action("touch_feed", lambda _params: {"feed_id": 1})

    result = executor.process_command(_action("touch_feed", "cmd-1"))

    assert result.success
    lines = _processing_lines(writer_records)
    assert len(lines) == 1
    assert lines[0][0] == logging.INFO
    assert "id=cmd-1" in lines[0][1]
