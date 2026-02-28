# Phase 10: Polish + Resume

**Status:** `pending`
**Estimated effort:** Day 19–20
**Depends on:** Phase 2 (manifest), Phase 3 (throttle)
**Blocks:** Nothing (final phase)

---

## Objective

Implement full manifest-based resume with diff logic, incremental re-runs, checksum skip option, and final CLI polish. After this phase, the tool handles interrupted downloads gracefully and supports incremental updates.

---

## Deliverables

### 1. Full Resume Logic (`--resume`)

**Reference:** [development-plan.md §11](development-plan.md#11-manifest--resume)

#### Resume Diff Algorithm

```python
def compute_resume_diff(manifest: Manifest, current_items: list[DriveItem]) -> ResumePlan:
    """Diff manifest against current Drive state."""
    plan = ResumePlan()
    current_ids = {item.id for item in current_items}

    for item in current_items:
        entry = manifest.get_file(item.id)
        if entry is None:
            plan.queue_new(item)                          # new file in Drive
        elif entry.status == "completed" and entry.modified_time == item.modified_time:
            plan.skip(item)                               # unchanged, skip
        elif entry.status == "completed" and entry.modified_time != item.modified_time:
            plan.queue_changed(item)                      # file changed, re-download
        elif entry.status in ("failed", "in_progress"):
            plan.queue_retry(item)                        # retry failed/interrupted
        elif entry.status == "pending":
            plan.queue_pending(item)                      # never started

    for file_id, entry in manifest.files.items():
        if file_id not in current_ids:
            plan.mark_deleted(file_id)                    # deleted from Drive

    return plan
```

#### Resume Flow

1. Load manifest → validate schema version
2. Walk Drive tree again (files may have changed)
3. Compute diff (skip completed+unchanged, re-queue changed/failed/new)
4. Download only queued files
5. Mark deleted files as `skipped` in manifest

### 2. Incremental Re-Run

Without `--resume` flag, if a manifest exists for the same source:
- Compare `modifiedTime` for each file
- Compare `md5Checksum` for blob files
- Only re-download files that have changed
- This is automatic — the manifest enables "sync-like" behavior

### 3. `--no-verify` Option

```python
@click.option("--no-verify", is_flag=True, help="Skip MD5 checksum verification")
```

- Skips `checksums.verify_checksum()` call
- Useful for speed on trusted networks
- Manifest still records `driveMd5Checksum` from API metadata

### 4. Manifest Schema Validation

```python
def _validate_manifest_schema(data: dict):
    """Validate manifest schema version. Raise ManifestError if incompatible."""
    version = data.get("schemaVersion")
    if version is None:
        raise ManifestError("Missing schema version in manifest")
    if version > CURRENT_SCHEMA_VERSION:
        raise ManifestError(
            f"Manifest schema v{version} is newer than supported v{CURRENT_SCHEMA_VERSION}. "
            "Please upgrade gdrive-dl."
        )
```

### 5. Corruption Handling

On `json.JSONDecodeError`:
- Print clear error: "Manifest file is corrupted"
- Suggest: "Run without --resume to start fresh, or restore from backup"
- Exit code 2
- Never attempt to partially load a corrupt manifest

### 6. Signal Handling

```python
import signal

def _setup_signal_handlers(manifest):
    def handler(signum, frame):
        manifest.save()  # Flush current state
        sys.exit(128 + signum)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
```

### 7. CLI Polish

- Review all `--help` text for clarity and completeness
- Consistent error message formatting
- Exit codes: 0=success, 1=partial failure (some files failed), 2=fatal error
- Version flag: `gdrive-dl --version`

### 8. CLI Options

```python
@click.option("--resume", is_flag=True, help="Resume interrupted download using manifest")
@click.option("--manifest", default="./gdrive-dl-manifest.json", help="Manifest file path")
@click.option("--no-verify", is_flag=True, help="Skip checksum verification")
@click.version_option(version=__version__)
```

---

## Tests (Write First)

### `test_manifest.py` (resume additions)

```python
# Resume diff
def test_resume_skip_completed_unchanged():
    """Completed file with same modifiedTime is skipped."""

def test_resume_requeue_completed_changed():
    """Completed file with different modifiedTime is re-queued."""

def test_resume_requeue_failed():
    """Failed file is re-queued for retry."""

def test_resume_requeue_in_progress():
    """In-progress file is re-queued."""

def test_resume_queue_new_file():
    """New file in Drive not in manifest is queued."""

def test_resume_mark_deleted():
    """File in manifest but not in Drive is marked skipped."""

def test_resume_pending_stays_queued():
    """Pending file remains in queue."""

# Schema validation
def test_manifest_schema_version_valid():
    """Valid schema version passes validation."""

def test_manifest_schema_version_too_new():
    """Newer schema version raises ManifestError with upgrade message."""

def test_manifest_schema_version_missing():
    """Missing schema version raises ManifestError."""

# Corruption
def test_corrupt_manifest_clear_error():
    """Corrupt JSON gives clear error message, not a traceback."""

def test_corrupt_manifest_exit_code_2():
    """Corrupt manifest results in exit code 2."""

# Signal handling
def test_sigint_flushes_manifest():
    """SIGINT handler saves manifest before exiting."""
```

### `test_cli.py` (polish additions)

```python
def test_version_flag():
    """--version prints version and exits."""

def test_exit_code_0_on_success():
    """Successful download returns exit code 0."""

def test_exit_code_1_on_partial_failure():
    """Some files failed returns exit code 1."""

def test_exit_code_2_on_fatal_error():
    """Fatal error (bad auth, bad source) returns exit code 2."""

def test_help_text_complete():
    """--help includes all documented options."""

def test_no_verify_skips_checksum():
    """--no-verify flag skips MD5 verification."""
```

---

## Verification Checklist

- [ ] `--resume` correctly skips completed+unchanged files
- [ ] `--resume` re-downloads changed files (different `modifiedTime`)
- [ ] `--resume` retries failed and in-progress files
- [ ] New files in Drive are discovered on resume
- [ ] Deleted files in Drive are marked `skipped` in manifest
- [ ] Corrupt manifest gives clear error and exit code 2
- [ ] Schema version mismatch gives upgrade suggestion
- [ ] SIGINT/SIGTERM flushes manifest before exit
- [ ] `--no-verify` skips checksum verification
- [ ] `--version` prints version
- [ ] Exit codes: 0 (success), 1 (partial), 2 (fatal)
- [ ] All `--help` text is clear and complete
- [ ] `pytest` — all tests pass
- [ ] Full regression test suite passes
