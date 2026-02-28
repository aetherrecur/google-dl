# Phase 8: Report Generation

**Status:** `completed`
**Estimated effort:** Day 17
**Depends on:** Phase 2 (walker + download)
**Blocks:** Nothing

---

## Objective

Implement post-download report generation in Markdown, HTML, and JSON formats. The report summarizes what was downloaded, skipped, failed, and any errors encountered.

---

## Deliverables

### 1. `ReportGenerator` in `report.py`

**Reference:** [development-plan.md §13](development-plan.md#13-reporting)

```python
class ReportGenerator:
    def __init__(self, stats: SessionStats, config: ResolvedConfig): ...

    def generate(self, format: str = "markdown") -> str:
        """Generate report in specified format."""

    def save(self, path: Path):
        """Write report to file."""
```

### 2. Report Sections

#### Session Metadata
- Start/end timestamps, duration
- Source folder name and ID
- Output directory path
- Config options used

#### Result Summary
- Total discovered, completed, skipped, failed
- Total bytes downloaded
- Checksum verification summary (passed/failed/skipped)

#### API Call Breakdown
- Walk calls, download calls
- Permissions calls, comments calls, revisions calls
- Total API calls made

#### Failed Files
- File name, Drive path, error reason
- Retry count before giving up

#### Skipped Files
- File name, skip reason (non-downloadable, already completed, filter excluded)

#### Type Breakdown
- Count and total size per MIME type category

### 3. Output Formats

#### Markdown (default)

```markdown
# gdrive-dl Download Report

## Session
- **Started:** 2026-02-28T14:00:00Z
- **Completed:** 2026-02-28T14:32:00Z
- **Duration:** 32 minutes
- **Source:** My Project Files (1ABC123xyz)

## Results
| Status | Count |
|--------|-------|
| Completed | 287 |
| Skipped | 18 |
| Failed | 7 |
| **Total** | **312** |

## Bytes Downloaded
1.8 GB

## Failed Files
| File | Path | Error |
|------|------|-------|
| budget.xlsx | /Finance/budget.xlsx | 403 cannotDownload |
```

#### HTML

Self-contained page with inline CSS. Readable in any browser offline. Same content structure as Markdown.

#### JSON

Machine-readable format for downstream tooling:

```json
{
  "session": { "started": "...", "completed": "...", "duration_seconds": 1920 },
  "source": { "name": "...", "id": "..." },
  "results": { "completed": 287, "skipped": 18, "failed": 7 },
  "bytes_downloaded": 1800000000,
  "api_calls": { "walk": 48, "download": 312, "permissions": 360 },
  "failed_files": [...],
  "skipped_files": [...],
  "type_breakdown": { "application/pdf": { "count": 142, "bytes": 890000000 } }
}
```

### 4. CLI Options

```python
@click.option("--report", is_flag=True, help="Generate download report after completion")
@click.option("--report-format", type=click.Choice(["markdown", "html", "json"]),
              default="markdown", help="Report output format")
```

### 5. Report File Naming

- Markdown: `gdrive-dl-report.md`
- HTML: `gdrive-dl-report.html`
- JSON: `gdrive-dl-report.json`

Saved in the output directory alongside downloaded files.

---

## Tests (Write First)

### `test_report.py` (post-download portion)

```python
# Markdown
def test_markdown_report_contains_session_info():
    """Markdown report includes start time, duration, source info."""

def test_markdown_report_result_table():
    """Markdown report includes completed/skipped/failed counts."""

def test_markdown_report_failed_files():
    """Failed files listed with path and error reason."""

# HTML
def test_html_report_self_contained():
    """HTML report includes inline CSS, no external dependencies."""

def test_html_report_same_content():
    """HTML report contains same data as Markdown report."""

# JSON
def test_json_report_valid_json():
    """JSON report is valid JSON that can be parsed."""

def test_json_report_structure():
    """JSON report has session, results, api_calls, failed_files keys."""

def test_json_report_machine_readable():
    """JSON report values are typed correctly (ints, not strings)."""

# General
def test_report_file_naming():
    """Report file uses correct extension for format."""

def test_report_saved_to_output_dir():
    """Report file saved in the output directory."""

def test_no_report_when_flag_not_set():
    """Without --report flag, no report file is generated."""

def test_report_with_zero_failures():
    """Report works correctly when no files failed."""

def test_report_with_all_failures():
    """Report works correctly when all files failed."""
```

---

## Verification Checklist

- [ ] `--report` generates Markdown report in output directory
- [ ] `--report-format html` generates self-contained HTML
- [ ] `--report-format json` generates valid, parseable JSON
- [ ] Report includes all sections (session, results, API calls, failures)
- [ ] Failed files list with specific error reasons
- [ ] Skipped files list with skip reasons
- [ ] Report works with 0 failures and 0 successes
- [ ] Report file naming follows convention
- [ ] `pytest tests/test_report.py` — all pass
