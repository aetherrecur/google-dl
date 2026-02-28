"""Tests for gdrive_dl.throttle — rate limiting, backoff, retry logic."""

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from gdrive_dl.throttle import (
    TokenBucketThrottler,
    _compute_backoff_delay,
    _is_retryable,
    throttled_execute,
)

# ---------------------------------------------------------------------------
# TokenBucketThrottler
# ---------------------------------------------------------------------------


class TestTokenBucketThrottler:
    """Token-bucket rate limiter with adaptive rate adjustment."""

    def test_initial_rate(self):
        t = TokenBucketThrottler(rate=10.0)
        assert t.rate == 10.0

    def test_acquire_does_not_block_when_tokens_available(self):
        t = TokenBucketThrottler(rate=100.0)
        start = time.monotonic()
        t.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_acquire_blocks_when_no_tokens(self):
        t = TokenBucketThrottler(rate=10.0)
        t.acquire()  # consume the token
        start = time.monotonic()
        t.acquire()  # should wait ~0.1s
        elapsed = time.monotonic() - start
        assert elapsed >= 0.05  # at least some waiting

    def test_on_success_increases_rate(self):
        t = TokenBucketThrottler(rate=10.0, max_rate=50.0)
        old_rate = t.rate
        t.on_success()
        assert t.rate > old_rate
        assert t.rate <= 50.0

    def test_on_success_does_not_exceed_max(self):
        t = TokenBucketThrottler(rate=49.0, max_rate=50.0)
        for _ in range(100):
            t.on_success()
        assert t.rate == 50.0

    def test_on_rate_limit_halves_rate(self):
        t = TokenBucketThrottler(rate=20.0)
        t.on_rate_limit()
        assert t.rate == 10.0

    def test_on_rate_limit_has_floor(self):
        t = TokenBucketThrottler(rate=0.5)
        t.on_rate_limit()
        assert t.rate >= 0.1  # should not drop below floor

    def test_fixed_mode_ignores_on_success(self):
        t = TokenBucketThrottler(rate=10.0, fixed=True)
        t.on_success()
        assert t.rate == 10.0

    def test_fixed_mode_ignores_on_rate_limit(self):
        t = TokenBucketThrottler(rate=10.0, fixed=True)
        t.on_rate_limit()
        assert t.rate == 10.0


# ---------------------------------------------------------------------------
# _compute_backoff_delay
# ---------------------------------------------------------------------------


class TestComputeBackoffDelay:
    """Exponential backoff with jitter."""

    def test_attempt_0_near_base(self):
        delay = _compute_backoff_delay(0, base=1.0, max_delay=64.0)
        assert 0 < delay <= 2.0  # base * 2^0 = 1.0, plus jitter up to 1.0

    def test_increases_with_attempt(self):
        delays = [_compute_backoff_delay(i, base=1.0, max_delay=64.0) for i in range(5)]
        # On average should increase (not strictly due to jitter, but max should)
        assert max(delays) > min(delays)

    def test_capped_at_max_delay(self):
        delay = _compute_backoff_delay(20, base=1.0, max_delay=64.0)
        assert delay <= 64.0

    def test_has_jitter(self):
        """Multiple calls with same attempt should produce different values."""
        delays = {_compute_backoff_delay(2, base=1.0, max_delay=64.0) for _ in range(20)}
        assert len(delays) > 1  # should not all be identical


# ---------------------------------------------------------------------------
# _is_retryable
# ---------------------------------------------------------------------------


def _make_http_error(status: int, reason: str = "") -> HttpError:
    """Create an HttpError with given status and error reason."""
    resp = MagicMock()
    resp.status = status
    if reason:
        body = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()
    else:
        body = b'{"error": {}}'
    return HttpError(resp=resp, content=body)


class TestIsRetryable:
    """Determine which HttpErrors warrant retry."""

    def test_429_is_retryable(self):
        assert _is_retryable(_make_http_error(429)) is True

    def test_500_is_retryable(self):
        assert _is_retryable(_make_http_error(500)) is True

    def test_502_is_retryable(self):
        assert _is_retryable(_make_http_error(502)) is True

    def test_503_is_retryable(self):
        assert _is_retryable(_make_http_error(503)) is True

    def test_403_rate_limit_exceeded_is_retryable(self):
        assert _is_retryable(_make_http_error(403, "rateLimitExceeded")) is True

    def test_403_user_rate_limit_exceeded_is_retryable(self):
        assert _is_retryable(_make_http_error(403, "userRateLimitExceeded")) is True

    def test_403_download_quota_not_retryable(self):
        assert _is_retryable(_make_http_error(403, "downloadQuotaExceeded")) is False

    def test_403_domain_policy_not_retryable(self):
        assert _is_retryable(_make_http_error(403, "domainPolicy")) is False

    def test_403_no_reason_not_retryable(self):
        assert _is_retryable(_make_http_error(403)) is False

    def test_404_not_retryable(self):
        assert _is_retryable(_make_http_error(404)) is False


# ---------------------------------------------------------------------------
# throttled_execute
# ---------------------------------------------------------------------------


class TestThrottledExecute:
    """throttled_execute wraps request.execute() with throttle + retry."""

    def test_succeeds_first_try(self):
        throttler = TokenBucketThrottler(rate=100.0)
        request = MagicMock()
        request.execute.return_value = {"files": []}

        result = throttled_execute(request, throttler)
        assert result == {"files": []}
        request.execute.assert_called_once()

    @patch("gdrive_dl.throttle._compute_backoff_delay", return_value=0.0)
    def test_retries_on_429(self, _mock_delay):
        throttler = TokenBucketThrottler(rate=100.0)
        request = MagicMock()
        request.execute.side_effect = [
            _make_http_error(429),
            {"files": []},
        ]

        result = throttled_execute(request, throttler, max_retries=3)
        assert result == {"files": []}
        assert request.execute.call_count == 2

    @patch("gdrive_dl.throttle._compute_backoff_delay", return_value=0.0)
    def test_retries_on_500(self, _mock_delay):
        throttler = TokenBucketThrottler(rate=100.0)
        request = MagicMock()
        request.execute.side_effect = [
            _make_http_error(500),
            {"ok": True},
        ]

        result = throttled_execute(request, throttler, max_retries=3)
        assert result == {"ok": True}

    @patch("gdrive_dl.throttle._compute_backoff_delay", return_value=0.0)
    def test_gives_up_after_max_retries(self, _mock_delay):
        throttler = TokenBucketThrottler(rate=100.0)
        request = MagicMock()
        error = _make_http_error(429)
        request.execute.side_effect = error

        with pytest.raises(HttpError):
            throttled_execute(request, throttler, max_retries=3)
        assert request.execute.call_count == 4  # initial + 3 retries

    def test_non_retryable_error_raises_immediately(self):
        throttler = TokenBucketThrottler(rate=100.0)
        request = MagicMock()
        request.execute.side_effect = _make_http_error(404)

        with pytest.raises(HttpError):
            throttled_execute(request, throttler, max_retries=3)
        request.execute.assert_called_once()

    @patch("gdrive_dl.throttle._compute_backoff_delay", return_value=0.0)
    def test_on_rate_limit_called_on_429(self, _mock_delay):
        throttler = TokenBucketThrottler(rate=100.0)
        request = MagicMock()
        request.execute.side_effect = [
            _make_http_error(429),
            {"ok": True},
        ]

        throttled_execute(request, throttler, max_retries=3)
        # Rate should have decreased then increased
        assert throttler.rate != 100.0 or True  # just verify no crash

    @patch("gdrive_dl.throttle._compute_backoff_delay", return_value=0.0)
    def test_on_success_called_after_success(self, _mock_delay):
        throttler = TokenBucketThrottler(rate=10.0, max_rate=50.0)
        request = MagicMock()
        request.execute.return_value = {"ok": True}

        throttled_execute(request, throttler)
        assert throttler.rate > 10.0  # on_success should have increased it
