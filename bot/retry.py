"""Retry helpers for functions that interact with remote services."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, TypeVar

from .youtube import CredentialsExpiredError, MissingGoogleDependenciesError

_T = TypeVar("_T")

_FAST_RETRY_DELAY_SECONDS = 5
_FAST_RETRY_ATTEMPTS = 10
_SLOW_RETRY_DELAYS = (60, 300, 600)
RETRY_WAIT_SECONDS: tuple[int, ...] = (
    (0,) + (_FAST_RETRY_DELAY_SECONDS,) * _FAST_RETRY_ATTEMPTS + _SLOW_RETRY_DELAYS
)
_NON_RETRYABLE_EXCEPTIONS = (
    CredentialsExpiredError,
    MissingGoogleDependenciesError,
)


async def call_with_retry(
    func: Callable[..., _T],
    *args: Any,
    description: str | None = None,
    **kwargs: Any,
) -> _T:
    """Execute ``func`` with retries and return its eventual result."""

    desc = description or getattr(func, "__name__", "operation")
    total_attempts = len(RETRY_WAIT_SECONDS)
    last_exc: BaseException | None = None

    for attempt, wait_seconds in enumerate(RETRY_WAIT_SECONDS, start=1):
        if attempt > 1 and wait_seconds:
            logging.info(
                "Retrying %s in %s seconds (attempt %s/%s)",
                desc,
                wait_seconds,
                attempt,
                total_attempts,
            )
            await asyncio.sleep(wait_seconds)

        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except _NON_RETRYABLE_EXCEPTIONS:
            raise
        except Exception as exc:  # pragma: no cover - exercised via tests
            last_exc = exc
            if attempt == total_attempts:
                break
            logging.warning(
                "Attempt %s/%s for %s failed: %s",
                attempt,
                total_attempts,
                desc,
                exc,
            )

    assert last_exc is not None  # We only exit loop on failure
    raise last_exc


__all__ = ["call_with_retry", "RETRY_WAIT_SECONDS"]
