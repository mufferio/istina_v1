"""
Rate limiting helper.

Purpose:
- Enforce request-per-minute (or similar) limits for external APIs.
- Prevent accidental quota exhaustion and reduce 429 errors.

Used by:
- gemini_provider.py (and any future providers)
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional


@dataclass
class RateLimiter:
    """
    Simple RPM (requests-per-minute) limiter.

    How to use:
        limiter = RateLimiter(rpm=60)
        limiter.acquire()  # call before each provider request

    Behavior:
        - Tracks timestamps of recent calls (rolling 60s window)
        - If you've already made `rpm` calls in the last 60 seconds,
          it sleeps until the window frees up, then proceeds.

    Notes:
        - Designed to be injectable/optional: pass limiter=None to skip throttling.
        - Thread-safety: not guaranteed (v0 single-threaded CLI is fine).
    """

    rpm: int
    window_seconds: float = 60.0
    _calls: Deque[float] = None  # type: ignore

    def __post_init__(self) -> None:
        if not isinstance(self.rpm, int) or self.rpm <= 0:
            raise ValueError("rpm must be a positive integer")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self._calls = deque()

    def acquire(self) -> None:
        """Block (sleep) until a request is allowed, then record the call."""
        now = time.monotonic()

        # Remove calls that are outside the rolling window
        cutoff = now - self.window_seconds
        while self._calls and self._calls[0] <= cutoff:
            self._calls.popleft()

        # If we're at/over limit, sleep until the oldest call exits the window
        if len(self._calls) >= self.rpm:
            oldest = self._calls[0]
            sleep_for = (oldest + self.window_seconds) - now
            if sleep_for > 0:
                time.sleep(sleep_for)

            # After sleeping, refresh and cleanup again
            now = time.monotonic()
            cutoff = now - self.window_seconds
            while self._calls and self._calls[0] <= cutoff:
                self._calls.popleft()

        # Record this call
        self._calls.append(time.monotonic())


def maybe_acquire(limiter: Optional[RateLimiter]) -> None:
    """
    Helper so callers can do:
        maybe_acquire(limiter)
    where limiter can be None.
    """
    if limiter is not None:
        limiter.acquire()