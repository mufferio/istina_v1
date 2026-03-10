"""
Retry helper.

Purpose:
- Provide a reusable retry mechanism for flaky operations:
  - network fetches (RSS)
  - provider calls (Gemini)
- Supports:
  - max attempts
  - exponential backoff
  - retryable exception types

Used by:
- rss_adapter.py
- gemini_provider.py
- analysis_service.py
"""
from __future__ import annotations

import time
from typing import Callable, Tuple, Type, TypeVar

T = TypeVar("T")


def retry(
        fn: Callable[[], T],
        exceptions: Tuple[Type[BaseException], ...] = (Exception,),
        max_attempts: int = 3,
        base_delay: float = 0.5,
        backoff_factor: float = 2.0,
        max_delay: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
) -> T:
    """
    Retry a callable with exponential backoff.

    Args:
        fn: Zero-arg function to execute.
        exceptions: Tuple of exception types to catch and retry on.
        max_attempts: Total attempts (initial try + retries). Must be >= 1.
        base_delay: Delay (seconds) before the 2nd attempt (after 1st failure). Must be >= 0.
        backoff_factor: Multiplier applied each subsequent failure. Must be >= 1.
        max_delay: Upper cap on delay between retries (seconds). Must be >= 0.
        sleep: Injected sleep function for testability (default: time.sleep).

    Behavior:
        - Calls fn up to max_attempts times.
        - If fn raises one of `exceptions`, waits then retries.
        - Delay schedule: base_delay, base_delay*backoff_factor, ... capped at max_delay.
        - If final attempt fails, re-raises the last caught exception.

    Example:
        >>> result = retry(flaky, exceptions=(TimeoutError,), max_attempts=5, base_delay=0.2)
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if base_delay < 0:
        raise ValueError("base_delay must be >= 0")
    if backoff_factor < 1:
        raise ValueError("backoff_factor must be >= 1")
    if max_delay < 0:
        raise ValueError("max_delay must be >= 0")

    delay = base_delay

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except exceptions:
            if attempt == max_attempts:
                raise
            if delay > 0:
                sleep(min(delay, max_delay))
            delay *= backoff_factor

    # Unreachable: loop always returns or raises on the final attempt.
    # Exists solely to satisfy type checkers (no implicit None return).
    raise AssertionError("retry: unreachable code reached")
