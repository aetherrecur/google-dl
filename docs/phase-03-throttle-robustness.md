# Phase 3: Throttle + Robustness

**Status:** `completed`
**Estimated effort:** Day 6–7
**Depends on:** Phase 2 (walker + download)
**Blocks:** Nothing (v0.1 complete after this phase)

---

## Objective

Implement adaptive rate limiting, exponential backoff with full jitter, and retry logic. Wrap every API call through the throttler. After this phase, the tool handles rate limits gracefully and constitutes the **Minimum Viable Product (v0.1)**.

---

## Deliverables

### 1. `throttle.py` — Rate Limiting + Backoff

**Reference:** [development-plan.md §8](development-plan.md#8-rate-limiting--resilience)

#### Token Bucket Rate Limiter

```python
class TokenBucketThrottler:
    def __init__(self, rate=10.0, max_rate=50.0):
        """rate: initial requests/sec. max_rate: ceiling."""

    def acquire(self):
        """Block until a token is available."""

    def on_success(self):
        """Gradually increase rate (5% toward max)."""

    def on_rate_limit(self):
        """Halve the rate (double the interval)."""
```

- Starting rate: 10 req/sec
- Max rate: 50 req/sec
- On 429/403-rateLimit: halve rate
- On success: 5% increase toward max
- Manual override via `--rate-limit N`

#### Exponential Backoff with Full Jitter

```python
def _compute_backoff_delay(attempt, base_delay=1.0, max_delay=64.0):
    """Full-jitter backoff per AWS/Google recommendations."""
    cap = min(max_delay, base_delay * (2 ** attempt))
    return random.uniform(0, cap)
```

#### Retryable vs Non-Retryable

| Status Code | Retryable? | Action |
|------------|-----------|--------|
| 429 | Yes | Backoff + retry |
| 500, 502, 503, 504 | Yes | Backoff + retry |
| 403 `rateLimitExceeded` | Yes | Backoff + retry |
| 403 `userRateLimitExceeded` | Yes | Backoff + retry |
| 403 `downloadQuotaExceeded` | No | Save manifest, exit cleanly |
| 403 `domainPolicy` | No | Skip file, log reason |
| 403 `cannotDownload` | No | Skip file, log reason |

#### API Call Wrapper

```python
def throttled_execute(request, throttler, max_retries=5):
    """Execute an API request with throttling and retry."""
    for attempt in range(max_retries + 1):
        throttler.acquire()
        try:
            result = request.execute()
            throttler.on_success()
            return result
        except HttpError as e:
            if _is_retryable(e) and attempt < max_retries:
                throttler.on_rate_limit()
                delay = _compute_backoff_delay(attempt)
                time.sleep(delay)
                continue
            raise
```

### 2. CLI Options

Add to `cli.py`:

```python
@click.option("--rate-limit", type=int, default=None,
              help="Max API requests per second (default: auto-throttle)")
@click.option("--retries", type=int, default=5,
              help="Max retry attempts on transient errors")
```

### 3. Integration with Existing Modules

- Wrap all `walker.py` API calls through `throttled_execute`
- Wrap all `downloader.py` API calls through `throttled_execute`
- Pass `throttler` instance from `DownloadRunner` to walker and downloader
- On `downloadQuotaExceeded`: save manifest and exit with informative message

### 4. Connection Error Recovery

- `MediaIoBaseDownload` cannot resume partial chunks
- On network error: delete `.partial` file, retry from byte 0 with backoff
- Distinguish network errors (`ConnectionError`, `TimeoutError`) from API errors

---

## Tests (Write First)

### `test_throttle.py`

```python
# Token bucket
def test_token_bucket_initial_rate():
    """Throttler starts at configured initial rate."""

def test_token_bucket_acquire_blocks():
    """acquire() blocks when tokens exhausted."""

def test_on_success_increases_rate():
    """on_success() increases rate by 5% toward max."""

def test_on_rate_limit_halves_rate():
    """on_rate_limit() halves the current rate."""

def test_manual_rate_override():
    """--rate-limit N sets fixed rate, disables adaptive behavior."""

# Backoff
def test_backoff_delay_within_bounds():
    """Backoff delay is between 0 and min(max_delay, base * 2^attempt)."""

def test_backoff_delay_has_jitter():
    """Multiple calls with same attempt produce different delays."""

def test_backoff_delay_capped_at_max():
    """Delay never exceeds max_delay."""

# Retryable detection
def test_429_is_retryable():
    """HTTP 429 is retryable."""

def test_500_is_retryable():
    """HTTP 500 is retryable."""

def test_403_rate_limit_is_retryable():
    """403 with rateLimitExceeded reason is retryable."""

def test_403_download_quota_not_retryable():
    """403 with downloadQuotaExceeded is NOT retryable."""

def test_403_domain_policy_not_retryable():
    """403 with domainPolicy is NOT retryable."""

# throttled_execute
def test_throttled_execute_retries_on_429():
    """On 429, retries up to max_retries with backoff."""

def test_throttled_execute_gives_up_after_max_retries():
    """After max_retries, raises the HttpError."""

def test_throttled_execute_succeeds_on_first_try():
    """Successful request returns result immediately."""
```

---

## Verification Checklist

- [ ] All API calls go through `throttled_execute`
- [ ] 429 responses trigger backoff and retry
- [ ] `downloadQuotaExceeded` saves manifest and exits cleanly
- [ ] `--rate-limit 5` caps at 5 requests/sec
- [ ] `--retries 3` limits retry attempts to 3
- [ ] Network errors trigger retry with backoff
- [ ] `.partial` files are cleaned up on network error retry
- [ ] Rate adjusts dynamically: decreases on rate limit, increases on success
- [ ] `pytest tests/test_throttle.py` — all pass
- [ ] `ruff check` and `mypy` — clean

---

## v0.1 Complete

After this phase, the following are working end-to-end:
- OAuth authentication (browser + no-browser)
- Recursive folder download preserving directory structure
- Workspace export (default formats)
- MD5 verification
- Basic manifest (resumable downloads)
- Rate limiting and retry
- Rich progress bar
