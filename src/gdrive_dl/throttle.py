"""Adaptive rate limiting and retry logic for Google Drive API calls."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

_MIN_RATE = 0.1  # floor: 1 request per 10 seconds
_RATE_INCREASE_FACTOR = 1.05  # +5% on success
_RETRYABLE_STATUSES = {429, 500, 502, 503}
_RETRYABLE_403_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}


class TokenBucketThrottler:
    """Simple token-bucket rate limiter with adaptive rate adjustment.

    Produces tokens at ``rate`` per second. ``acquire()`` blocks until a
    token is available.  On success the rate creeps up toward ``max_rate``;
    on a rate-limit signal the rate is halved.  Setting ``fixed=True``
    disables adaptive behaviour (useful with ``--rate-limit``).
    """

    def __init__(
        self,
        rate: float = 10.0,
        max_rate: float = 50.0,
        fixed: bool = False,
    ) -> None:
        self.rate = rate
        self.max_rate = max_rate
        self._fixed = fixed
        self._last_time = time.monotonic()

    def acquire(self) -> None:
        """Block until a token is available."""
        interval = 1.0 / self.rate
        now = time.monotonic()
        elapsed = now - self._last_time
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_time = time.monotonic()

    def on_success(self) -> None:
        """Nudge rate up by 5% toward max (no-op if fixed)."""
        if self._fixed:
            return
        self.rate = min(self.rate * _RATE_INCREASE_FACTOR, self.max_rate)

    def on_rate_limit(self) -> None:
        """Halve rate on rate-limit signal (no-op if fixed)."""
        if self._fixed:
            return
        self.rate = max(self.rate / 2.0, _MIN_RATE)


def _compute_backoff_delay(
    attempt: int,
    base: float = 1.0,
    max_delay: float = 64.0,
) -> float:
    """Exponential backoff with full jitter, capped at *max_delay*."""
    exp_delay = base * (2 ** attempt)
    capped = min(exp_delay, max_delay)
    return random.uniform(0, capped)  # noqa: S311


def _is_retryable(exc: HttpError) -> bool:
    """Return True if *exc* represents a transient / rate-limit error."""
    status = exc.resp.status
    if status in _RETRYABLE_STATUSES:
        return True
    if status == 403:
        try:
            body = json.loads(exc.content.decode("utf-8"))
            errors = body.get("error", {}).get("errors", [])
            return any(e.get("reason") in _RETRYABLE_403_REASONS for e in errors)
        except Exception:
            return False
    return False


def throttled_execute(
    request: Any,
    throttler: TokenBucketThrottler,
    max_retries: int = 5,
) -> dict[str, Any]:
    """Execute a Google API *request* with throttle, backoff, and retry.

    Acquires a token before each attempt.  On retryable ``HttpError`` the
    throttler is signalled and the call is retried with exponential backoff.
    Non-retryable errors are re-raised immediately.
    """
    last_exc: HttpError | None = None

    for attempt in range(max_retries + 1):
        throttler.acquire()
        try:
            result = request.execute()
            throttler.on_success()
            return result  # type: ignore[no-any-return]
        except HttpError as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
            throttler.on_rate_limit()
            if attempt < max_retries:
                delay = _compute_backoff_delay(attempt)
                logger.warning(
                    "Retryable error (attempt %d/%d, status %s), "
                    "backing off %.1fs: %s",
                    attempt + 1,
                    max_retries + 1,
                    exc.resp.status,
                    delay,
                    exc,
                )
                time.sleep(delay)

    raise last_exc  # type: ignore[misc]
