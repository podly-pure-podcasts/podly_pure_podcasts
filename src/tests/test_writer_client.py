from queue import Empty, Queue
from types import SimpleNamespace

import pytest

from app import _get_sqlite_busy_timeout_ms
from app.db_timeouts import SQLITE_BUSY_TIMEOUT_MS
from app.writer.client import (
    WRITER_REPLY_MARGIN_SEC,
    WriterClient,
    writer_reply_timeout_sec,
)
from app.writer.protocol import WriteCommand, WriteCommandType, WriteResult


class _ReplyQueue:
    def __init__(self, reply: WriteResult | None = None) -> None:
        self.reply = reply
        self.timeout: float | None = None

    def get(self, timeout: float) -> WriteResult:
        self.timeout = timeout
        if self.reply is None:
            raise Empty
        return self.reply


def _submit(reply_q: _ReplyQueue, **kwargs: float) -> WriteResult | None:
    client = WriterClient()
    client.queue = Queue()
    client.manager = SimpleNamespace(Queue=lambda: reply_q)
    cmd = WriteCommand(id="cmd", type=WriteCommandType.ACTION, model=None, data={})
    return client.submit(cmd, wait=True, **kwargs)


def test_the_default_reply_wait_is_the_busy_timeout_plus_the_margin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PODLY_WRITER_REPLY_TIMEOUT_SEC", raising=False)
    assert _get_sqlite_busy_timeout_ms() == SQLITE_BUSY_TIMEOUT_MS
    expected = SQLITE_BUSY_TIMEOUT_MS / 1000 + WRITER_REPLY_MARGIN_SEC
    assert writer_reply_timeout_sec() == expected

    # A write can wait for the SQLite lock up to busy_timeout before it runs,
    # so a shorter reply wait fails writes that later commit (#267).
    reply_q = _ReplyQueue(WriteResult("cmd", True))
    result = _submit(reply_q)
    assert result is not None and result.success
    assert reply_q.timeout == expected
    assert expected * 1000 > SQLITE_BUSY_TIMEOUT_MS


def test_the_environment_overrides_the_reply_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PODLY_WRITER_REPLY_TIMEOUT_SEC", "15")
    reply_q = _ReplyQueue(WriteResult("cmd", True))
    _submit(reply_q)
    assert reply_q.timeout == 15.0


def test_no_reply_within_the_wait_raises_timeout_error() -> None:
    reply_q = _ReplyQueue()
    with pytest.raises(TimeoutError, match="Writer service did not respond"):
        _submit(reply_q, timeout=0.01)
    assert reply_q.timeout == 0.01
