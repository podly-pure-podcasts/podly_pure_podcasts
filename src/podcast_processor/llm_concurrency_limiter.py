"""
LLM concurrency limiter to control the number of simultaneous LLM API calls.

This module provides a semaphore-based concurrency control mechanism to prevent
too many simultaneous LLM API calls, which can help avoid rate limiting and
improve system stability.
"""

import logging
import threading
<<<<<<< HEAD
from typing import Any
=======
from typing import Any, Optional
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e

logger = logging.getLogger(__name__)


class LLMConcurrencyLimiter:
    """Controls the number of concurrent LLM API calls using a semaphore."""

    def __init__(self, max_concurrent_calls: int):
        """
        Initialize the concurrency limiter.

        Args:
            max_concurrent_calls: Maximum number of simultaneous LLM API calls allowed
        """
        if max_concurrent_calls <= 0:
            raise ValueError("max_concurrent_calls must be greater than 0")

        self.max_concurrent_calls = max_concurrent_calls
        self._semaphore = threading.Semaphore(max_concurrent_calls)

        logger.info(
            f"LLM concurrency limiter initialized with {max_concurrent_calls} max concurrent calls"
        )

<<<<<<< HEAD
    def acquire(self, timeout: float | None = None) -> bool:
=======
    def acquire(self, timeout: Optional[float] = None) -> bool:
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        """
        Acquire a slot for making an LLM API call.

        Note: Consider using ConcurrencyContext for automatic resource management.

        Args:
            timeout: Maximum time to wait for a slot in seconds. None means wait indefinitely.

        Returns:
            True if a slot was acquired, False if timeout occurred
        """
<<<<<<< HEAD
        acquired = self._semaphore.acquire(timeout=timeout)
=======
        # Disable specific pylint warning for this line as manual semaphore control is needed
        acquired = self._semaphore.acquire(  # pylint: disable=consider-using-with
            timeout=timeout
        )
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        if acquired:
            logger.debug("Acquired LLM concurrency slot")
        else:
            logger.warning(
                f"Failed to acquire LLM concurrency slot within {timeout}s timeout"
            )
        return acquired

    def release(self) -> None:
        """
        Release a slot after completing an LLM API call.

        Note: Consider using ConcurrencyContext for automatic resource management.
        """
        self._semaphore.release()
        logger.debug("Released LLM concurrency slot")

    def get_available_slots(self) -> int:
        """Get the number of currently available slots."""
        return self._semaphore._value

    def get_active_calls(self) -> int:
        """Get the number of currently active LLM calls."""
        return self.max_concurrent_calls - self._semaphore._value


# Global concurrency limiter instance
<<<<<<< HEAD
_CONCURRENCY_LIMITER: LLMConcurrencyLimiter | None = None
=======
_concurrency_limiter: Optional[LLMConcurrencyLimiter] = None
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e


def get_concurrency_limiter(max_concurrent_calls: int = 3) -> LLMConcurrencyLimiter:
    """Get or create the global concurrency limiter instance."""
<<<<<<< HEAD
    global _CONCURRENCY_LIMITER
    if (
        _CONCURRENCY_LIMITER is None
        or _CONCURRENCY_LIMITER.max_concurrent_calls != max_concurrent_calls
    ):
        _CONCURRENCY_LIMITER = LLMConcurrencyLimiter(max_concurrent_calls)
    return _CONCURRENCY_LIMITER
=======
    global _concurrency_limiter  # pylint: disable=global-statement
    if (
        _concurrency_limiter is None
        or _concurrency_limiter.max_concurrent_calls != max_concurrent_calls
    ):
        _concurrency_limiter = LLMConcurrencyLimiter(max_concurrent_calls)
    return _concurrency_limiter
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e


class ConcurrencyContext:
    """Context manager for controlling LLM API call concurrency."""

<<<<<<< HEAD
    def __init__(self, limiter: LLMConcurrencyLimiter, timeout: float | None = None):
=======
    def __init__(self, limiter: LLMConcurrencyLimiter, timeout: Optional[float] = None):
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
        """
        Initialize the context manager.

        Args:
            limiter: The concurrency limiter to use
            timeout: Maximum time to wait for a slot
        """
        self.limiter = limiter
        self.timeout = timeout
        self.acquired = False

    def __enter__(self) -> "ConcurrencyContext":
        """Acquire a concurrency slot."""
        self.acquired = self.limiter.acquire(timeout=self.timeout)
        if not self.acquired:
            raise RuntimeError(
                f"Could not acquire LLM concurrency slot within {self.timeout}s"
            )
        return self

    def __exit__(
        self,
<<<<<<< HEAD
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
=======
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
>>>>>>> 3eb2779c9f2e56f05d9c9c4a67c02f1c83384b8e
    ) -> None:
        """Release the concurrency slot."""
        if self.acquired:
            self.limiter.release()
