import functools
import threading
from collections.abc import Callable
from typing import Any, TypeVar, cast

T = TypeVar("T")


class TimeoutException(Exception):
    """Custom exception to indicate a timeout."""


def timeout_decorator(timeout: int) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to enforce a timeout on a function.
    If the function execution exceeds the timeout, a TimeoutException is raised.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            timeout_flag = threading.Event()
            pending = object()
            result: list[object] = [pending]

            def target() -> None:
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    print(f"Exception in thread: {e}")
                finally:
                    timeout_flag.set()

            thread = threading.Thread(target=target)
            thread.start()
            thread.join(timeout)
            if not timeout_flag.is_set():
                func_name = getattr(func, "__name__", "<callable>")
                raise TimeoutException(
                    f"Function '{func_name}' exceeded timeout of {timeout} seconds."
                )
            if result[0] is pending:
                raise TimeoutException(
                    "Function did not return a value before timeout handling completed."
                )
            return cast(T, result[0])

        return wrapper

    return decorator
