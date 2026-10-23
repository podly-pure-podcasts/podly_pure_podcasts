"""In-process writer client for tests.

Keep this out of shared/test_utils.py: pytest collects test_*.py modules.
"""

from typing import Any

from app.writer.client import writer_client


def force_local_writer() -> None:
    """Execute writer commands in-process so tests never hit the live writer."""

    def _submit(cmd: Any, wait: bool = False, timeout: int = 10) -> Any:
        del timeout
        result = writer_client._local_execute(cmd)
        return result if wait else None

    writer_client.submit = _submit  # type: ignore[method-assign]
