# Phase 5: Dry-Run Report

**Status:** `pending`
**Estimated effort:** Day 10
**Depends on:** Phase 2 (walker + download), Phase 4 (filtering — optional)
**Blocks:** Nothing

---

## Objective

Implement the `--dry-run` flag that traverses the directory tree and collects metadata without downloading, then displays a comprehensive Rich table report showing file counts, estimated sizes, API call predictions, and non-downloadable items.

---

## Deliverables

### 1. Dry-Run Execution Flow

**Reference:** [development-plan.md §3](development-plan.md#3-cli-design)

`dry_run=True` is threaded through all modules:
- Walker and filter code runs normally (metadata is fetched)
- Downloader receives flag and suppresses all writes, returning `DRY_RUN` status per file
- Manifest is read (for resume comparison) but never written
- Archival module estimates API call counts without making the calls

### 2. `DryRunReporter` in `report.py`

**Reference:** [development-plan.md §13](development-plan.md#13-reporting)

```python
class DryRunReporter:
    def __init__(self, items: list[DriveItem], config: ResolvedConfig): ...

    def generate(self) -> str:
        """Generate and display dry-run report."""
```

#### Report Sections

1. **Source info** — folder name, folder ID
2. **File counts** — directories, downloadable files, Workspace files, non-downloadable items, shortcuts
3. **Size estimate** — total bytes for blob files, "unknown until download" for Workspace
4. **API call estimate** — broken down by operation (walk, download, permissions, comments, revisions)
5. **Time estimate** — predicted wall-clock time at current quota rate
6. **Quota headroom** — percentage of 12,000 req/60s quota available
7. **Files by type** — count and size per MIME type category
8. **Non-downloadable items** — list with reasons (Google Forms, Sites, etc.)
9. **Filter effects** — files excluded by filters, conditionally included items

#### Rich Table Output

Use `rich.table.Table` and `rich.console.Console`:

```python
from rich.console import Console
from rich.table import Table

def _display_report(self):
    console = Console()

    # Summary panel
    console.print(f"Source: {self.folder_name} ({self.folder_id})")
    console.print(f"Directories: {self.dir_count}")
    console.print(f"Downloadable: {self.file_count} files ({self.size_estimate})")
    ...

    # Type breakdown table
    table = Table(title="Files by type")
    table.add_column("Type")
    table.add_column("Count", justify="right")
    table.add_column("Size", justify="right")
    for type_name, count, size in self.type_breakdown:
        table.add_row(type_name, str(count), format_bytes(size))
    console.print(table)
```

### 3. API Call Estimation

```python
def estimate_api_calls(items, config) -> dict:
    """Estimate API calls by operation type."""
    calls = {
        "walk": walk_page_count,
        "download": downloadable_count,
        "permissions": file_count if config.permissions else 0,
        "comments": files_with_comments if config.comments else 0,
        "revisions": file_count if config.revisions is not None else 0,
    }
    return calls
```

### 4. `SessionStats` Dataclass

```python
@dataclass
class SessionStats:
    total_discovered: int = 0
    total_completed: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    total_bytes_downloaded: int = 0
    api_calls_walk: int = 0
    api_calls_download: int = 0
    api_calls_permissions: int = 0
    api_calls_comments: int = 0
    api_calls_revisions: int = 0
    type_counts: dict[str, int]
    type_sizes: dict[str, int]
    failed_files: list
    non_downloadable_items: list[dict]
```

---

## Tests (Write First)

### `test_report.py` (dry-run portion)

```python
def test_dry_run_report_file_counts():
    """Report correctly counts files, folders, and non-downloadable items."""

def test_dry_run_report_size_estimate():
    """Size estimate sums blob file sizes correctly."""

def test_dry_run_report_workspace_size_unknown():
    """Workspace files show 'unknown' for size estimate."""

def test_dry_run_report_api_call_estimate():
    """API call count matches expected breakdown by operation."""

def test_dry_run_report_with_permissions():
    """--permissions doubles estimated API calls."""

def test_dry_run_report_non_downloadable_listed():
    """Non-downloadable items appear with MIME type and reason."""

def test_dry_run_report_type_breakdown():
    """Files grouped by type with correct counts and sizes."""

def test_dry_run_no_manifest_write():
    """In dry-run mode, manifest is never written to disk."""

def test_dry_run_no_file_download():
    """In dry-run mode, no files are written to disk."""

def test_dry_run_with_filter_shows_conditional():
    """Expensive filter predicates show items as 'conditionally included'."""
```

---

## Verification Checklist

- [ ] `gdrive-dl --dry-run <SOURCE>` shows report without downloading
- [ ] File counts match actual folder contents
- [ ] Size estimates are reasonable for blob files
- [ ] API call estimates are accurate
- [ ] Non-downloadable items listed with reasons
- [ ] `--permissions`, `--comments`, `--revisions` flags increase API call estimates
- [ ] No files written to disk in dry-run mode
- [ ] No manifest written in dry-run mode
- [ ] Rich formatted output renders correctly in terminal
- [ ] `pytest tests/test_report.py` — all pass

---

## Example Output

```
gdrive-dl dry run report
========================

Source:          My Project Files (1ABC123xyz)
Directories:     47
Downloadable:    312 files (1.8 GB estimated)
Workspace files: 23 files (exported size unknown until download)
Non-downloadable: 3 items (2 Google Forms, 1 Google Site)
Shortcuts:       5 (resolved to targets)

Estimated API calls:  ~360  (312 downloads + 47 listings + 1 walk)
Estimated time:       ~2 min at current quota (12,000 req/60s)
Quota headroom:       97% available

Files by type:
  PDF:           142  (890 MB)
  Images:         87  (620 MB)
  Google Docs:    15  (export to .docx)
  Google Sheets:   6  (export to .xlsx)
  Google Slides:   2  (export to .pptx)
  Other:          63  (290 MB)

Non-downloadable items:
  /forms/Q3 Survey          (Google Form — cannot be exported)
  /forms/Feedback           (Google Form — cannot be exported)
  /sites/Team Wiki          (Google Site — cannot be exported)
```
