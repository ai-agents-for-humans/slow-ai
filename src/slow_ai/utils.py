"""
Shared utility helpers.
"""
import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_async(
    coro_fn: Callable[[], Coroutine[Any, Any, T]],
    max_attempts: int = 3,
    base_delay: float = 2.0,
    retryable: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Retry an async coroutine with exponential backoff.

    Args:
        coro_fn:      Zero-argument callable that returns a fresh coroutine each call.
        max_attempts: Maximum number of attempts (including the first).
        base_delay:   Seconds to wait before the second attempt; doubles each retry.
        retryable:    Exception types that trigger a retry. Others are re-raised immediately.

    Raises:
        The last exception if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn()
        except retryable as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Attempt %d/%d failed (%s: %s). Retrying in %.1fs…",
                attempt, max_attempts, type(exc).__name__, exc, delay,
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
