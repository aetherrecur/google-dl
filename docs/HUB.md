# gdrive-dl: Development Hub

Central development document for the `gdrive-dl` project. All implementation work flows through this hub.

---

## Quick Links

| Document | Purpose |
|----------|---------|
| [Product Spec](product-spec.md) | Feature requirements, CLI interface, usage examples |
| [Development Plan](development-plan.md) | Architecture, data structures, module design, API integration |
| [Python Clean Code](python-clean-code.md) | Coding standards and patterns |
| [OAuth Browser Launch](oauth-browser-launch.md) | Browser detection and OAuth flow research |
| [Drive Download API](drive-download-api.md) | Google Drive API traversal and download mechanics |

---

## Project Overview

**gdrive-dl** is a Python CLI tool for downloading and archiving Google Drive directories with full context preservation — files, permissions, comments, revision history, and metadata.

### Technology Stack

| Component | Choice | Reference |
|-----------|--------|-----------|
| Language | Python 3.9+ | — |
| CLI framework | Click 8.x | [Development Plan §3](development-plan.md#3-cli-design) |
| Build backend | hatchling | [Development Plan §2](development-plan.md#2-project-scaffolding) |
| Progress/output | Rich | [Development Plan §2](development-plan.md#2-project-scaffolding) |
| Google API client | google-api-python-client + google-auth-oauthlib | [Development Plan §5](development-plan.md#5-authentication-module) |
| Project layout | src-layout (`src/gdrive_dl/`) | [Development Plan §2](development-plan.md#2-project-scaffolding) |

### Module Architecture

```
cli.py → config.py, auth.py, walker.py, filters.py, downloader.py, archival.py, manifest.py, report.py
                                  ↑                        ↑                ↑
                          throttle.py              checksums.py      timestamps.py
                          exceptions.py            constants.py
```

Dependency flows one direction: `cli.py` → orchestration modules → utility leaf modules. No circular imports.

---

## Coding Standards

All code must follow the conventions in [python-clean-code.md](python-clean-code.md). Key requirements:

### Naming
- Variables/functions: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Classes: `PascalCase`
- Booleans: `is_`, `has_`, `can_`, `should_` prefixes

### Structure
- Guard clauses and early returns over deep nesting
- Maximum 3 levels of nesting
- Functions prefer <30 lines
- Prefer <5 parameters per function
- Explicit parentheses in complex conditionals — always parenthesize compound `and`/`or` conditions
- Use `Enum` for magic strings (status values, drive types, MIME categories) — never compare against raw string literals
- **Law of Demeter** — ask objects for behavior, don't reach into their internals; never chain method calls or access nested attributes directly (e.g., use `manifest.all_entries()` not `manifest.files.items()`)

### Imports
- Organized: stdlib → third-party → local
- One import per line, alphabetized within groups
- Absolute imports preferred
- No wildcard imports
- Use `TYPE_CHECKING` guard for type-hint-only imports

### Principles
- **SOLID** — Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
- **DRY** — No duplicate logic
- **KISS** — Straightforward solutions
- **YAGNI** — Only implement what is currently required
- **Fail Fast** — Validate inputs early, raise at point of failure
- **Composition over Inheritance** — Build behavior by combining objects

---

## Test-Driven Development

### TDD Workflow

For every module:

1. **Write tests first** — Define expected behavior before implementation
2. **Red** — Run tests, confirm they fail (proves the test is meaningful)
3. **Green** — Write the minimum code to pass the tests
4. **Refactor** — Clean up while keeping tests green

### Test Organization

```
tests/
├── __init__.py
├── conftest.py            # Shared fixtures: mock Drive API, temp dirs, sample DriveItems
├── test_auth.py           # OAuth flow, token lifecycle, service account, browser selection
├── test_walker.py         # BFS traversal, pagination, shortcuts, name collisions
├── test_downloader.py     # Blob download, Workspace export, partial files, >10MB fallback
├── test_filters.py        # API query building, post-fetch predicates, cost estimation
├── test_manifest.py       # Read/write, atomic flushes, resume diff logic, corruption
├── test_config.py         # YAML loading, merge precedence, ExportConfig
├── test_checksums.py      # MD5/SHA-256 verification, mismatch handling
├── test_timestamps.py     # mtime/atime application, directory bottom-up ordering
├── test_throttle.py       # Token bucket, backoff calculation, jitter, retryable codes
├── test_report.py         # Dry-run report, post-download report, output formats
├── test_archival.py       # Permissions, comments, revisions sidecar generation
├── test_exceptions.py     # Exception hierarchy, error message formatting
├── test_constants.py      # MIME mappings, export format defaults
└── test_cli.py            # CLI integration via click.testing.CliRunner
```

### Testing Principles

- **Unit tests** for leaf modules (`constants.py`, `checksums.py`, `timestamps.py`, `throttle.py`, `exceptions.py`) — no mocking needed
- **Mock-based tests** for API-dependent modules (`auth.py`, `walker.py`, `downloader.py`, `archival.py`) — mock `googleapiclient` responses
- **Integration tests** for CLI (`test_cli.py`) — use `click.testing.CliRunner`; add tests for each CLI option as it's introduced (not deferred to Phase 10)
- **Regression tests** — when a bug is found, write a test that reproduces it before fixing; when adding a new phase, verify prior phase tests still pass with new integration code
- **Fixtures in `conftest.py`** — shared test data, expanded incrementally across phases

### Required Shared Fixtures (`conftest.py`)

Expand as phases are implemented:

```python
@pytest.fixture
def tmp_output_dir(tmp_path): ...             # Phase 0+

@pytest.fixture
def sample_drive_item(): ...                   # Phase 0+ (blob file)

@pytest.fixture
def sample_drive_item_workspace(): ...         # Phase 2+ (Google Docs MIME)

@pytest.fixture
def sample_drive_item_folder(): ...            # Phase 2+ (is_folder=True)

@pytest.fixture
def sample_drive_item_shortcut(): ...          # Phase 2+ (is_shortcut=True)

@pytest.fixture
def mock_drive_service(): ...                  # Phase 1+ (MagicMock of Drive API Resource)

@pytest.fixture
def mock_credentials(): ...                    # Phase 1+ (controllable valid/expired/refresh)

@pytest.fixture
def mock_throttler(): ...                      # Phase 3+ (no-op throttler for non-throttle tests)

@pytest.fixture
def sample_manifest(tmp_path): ...             # Phase 10 (mix of completed/failed/pending entries)

@pytest.fixture
def temp_manifest_file(tmp_path): ...          # Phase 2+ (writable manifest JSON path)
```

### Mock Strategy

| Module | What to Mock |
|--------|-------------|
| `auth.py` | `google.oauth2.credentials.Credentials`, `InstalledAppFlow`, `googleapiclient.discovery.build` |
| `walker.py` | `service.files().list().execute()`, `service.files().get().execute()` |
| `downloader.py` | `MediaIoBaseDownload`, `requests.get` (for exportLinks) |
| `archival.py` | `service.permissions().list()`, `service.comments().list()`, `service.revisions().list()` |
| `throttle.py` | `time.sleep` (prevent slow tests), `random.uniform` (deterministic jitter tests) |
| `timestamps.py` | Real temp files OK; mock `subprocess.run` for macOS `SetFile` |
| `config.py` | Filesystem (`tmp_path`), environment variables (`monkeypatch`) |

### Test Coverage Requirements

- Minimum 80% line coverage for each module
- 100% coverage for `exceptions.py` and `constants.py` (pure data, no excuses)
- Every error path must have a test (not just the happy path)
- Edge cases: empty folders, zero-byte files, Unicode filenames, name collisions, expired tokens

### What to Test Per Module

| Module | Key Test Scenarios |
|--------|--------------------|
| `exceptions.py` | Hierarchy (`isinstance` checks), error message formatting, `file_id`/`name` on `DownloadError` |
| `constants.py` | MIME map completeness, export format defaults, `NON_DOWNLOADABLE` set membership |
| `auth.py` | Valid token reuse, expired token refresh, missing token → browser flow, scope mismatch detection, service account path, `about.get` smoke test |
| `walker.py` | Single folder, nested BFS, pagination (multiple pages), shortcuts with cycle detection, name collision dedup, Shared Drive kwargs |
| `downloader.py` | Blob download (small/large chunks), Workspace export, >10MB `exportLinks` fallback, `.partial` file lifecycle, non-downloadable skip |
| `filters.py` | API query injection, free predicates (size, ext, name), expensive predicates (cost estimation), evaluation order, `--filter-confirm` guard |
| `manifest.py` | Create new, load existing, atomic write, resume diff (completed/changed/failed/new/deleted), corruption handling |
| `checksums.py` | MD5 match, MD5 mismatch → retry, Workspace file (no checksum) |
| `timestamps.py` | `mtime` set correctly, directory bottom-up ordering |
| `throttle.py` | Token bucket rate, backoff calculation with jitter bounds, retryable vs non-retryable status codes |
| `config.py` | YAML parse, merge precedence (config < CLI), nested export overrides, missing file handling |
| `report.py` | Dry-run table generation, post-download summary, JSON/Markdown/HTML output |
| `archival.py` | Permissions sidecar format, comments with replies, revisions listing and download, best-effort error handling |
| `cli.py` | `--dry-run` flag threading, `--help` output, invalid source error, config file loading |

---

## Implementation Phases

| Phase | Document | Status | Description |
|-------|----------|--------|-------------|
| 0 | [phase-00-project-skeleton.md](phase-00-project-skeleton.md) | `completed` | pyproject.toml, exceptions, constants, .gitignore |
| 1 | [phase-01-auth.md](phase-01-auth.md) | `completed` | OAuth2 flow, browser launch, Drive metadata smoke test |
| 2 | [phase-02-walker-download.md](phase-02-walker-download.md) | `completed` | BFS traversal, blob/Workspace download, manifest, progress |
| 3 | [phase-03-throttle-robustness.md](phase-03-throttle-robustness.md) | `completed` | Rate limiting, exponential backoff, retry logic |
| 4 | [phase-04-filtering.md](phase-04-filtering.md) | `completed` | API query pushdown, post-fetch filters, cost guard |
| 5 | [phase-05-dry-run.md](phase-05-dry-run.md) | `completed` | Dry-run report with Rich tables |
| 6 | [phase-06-archival.md](phase-06-archival.md) | `completed` | Permissions, comments, metadata, revisions |
| 7 | [phase-07-config.md](phase-07-config.md) | `completed` | YAML config loading, export format overrides |
| 8 | [phase-08-reports.md](phase-08-reports.md) | `pending` | Post-download report generation (MD/HTML/JSON) |
| 9 | [phase-09-shared-drives.md](phase-09-shared-drives.md) | `pending` | Shared Drive support, auto-discovery |
| 10 | [phase-10-polish-resume.md](phase-10-polish-resume.md) | `pending` | Full resume logic, incremental re-runs, final polish |

### Minimum Viable Product (v0.1)

Phases 0–3 deliver v0.1:
- OAuth authentication (browser + no-browser)
- Recursive folder download preserving directory structure
- Workspace export (default formats)
- MD5 verification
- Basic manifest (resumable downloads)
- Rate limiting and retry
- Rich progress bar

### Parallel Development Opportunities

After Phases 0–2, these are fully independent:
- `filters.py` (Phase 4)
- `archival.save_permissions` / `archival.save_comments` / `archival.save_metadata` (Phase 6)
- `config.py` YAML loading (Phase 7)
- Dry-run report (Phase 5)
- Report generation (Phase 8)

---

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Project layout | src-layout | Prevents accidental uninstalled imports |
| Build backend | hatchling | Modern, minimal pyproject.toml |
| CLI framework | Click 8.x | Optional-value flags, `ctx.default_map`, repeatable key=value |
| Traversal | BFS | Avoids recursion limit, predictable memory |
| Partial files | `.partial` + atomic rename | Prevents incomplete files being treated as complete |
| Manifest key | `fileId` (not path) | Resume works even if output dir moves |
| Rate limiting | Adaptive throttle + full-jitter backoff | Follows Google/AWS guidelines |
| Error strategy | Custom hierarchy, catch at boundary | Per-file non-fatal; auth/source fatal |
| OAuth scope | `drive.readonly` | Minimum required; never request write scope |

---

## Error Handling Strategy

```
GdriveError (base)
├── AuthError              → fatal, exit with clear message
├── SourceNotFoundError    → fatal, exit
├── ConfigError            → fatal, exit
├── DownloadError          → per-file, log to manifest, continue
├── ChecksumError          → per-file, retry then warn/fail
├── RateLimitError         → retry internally in throttle.py
├── FilterCostError        → prompt user or exit
└── ManifestError          → exit with recovery instructions
```

| Location | Catch | Propagate |
|----------|-------|-----------|
| `throttle.py` | `HttpError 429/403` | Never — retry internally |
| `downloader.py` per-file | `DownloadError`, `ChecksumError` | Never — log to manifest |
| `archival.py` per-file | All `GdriveError` | Never — best-effort |
| `auth.py` | Never | `AuthError` — fatal |
| `cli.main()` | Fatal errors | Convert to `click.ClickException` |

---

## Verification Gaps & Notes

Items identified during document review that require attention during implementation:

### Features Requiring Phase Assignment

These product spec features exist in `ResolvedConfig` but need explicit implementation:

| Feature | Where to Implement | Notes |
|---------|-------------------|-------|
| `--flat` | Phase 2 (walker/downloader) | Flatten all files into single directory; handle name collisions |
| `--quiet` | Phase 2 (progress), Phase 8 (report) | Suppress Rich progress output |
| `--verbose` | Phase 1+, all API modules | Per-file logging, API call traces; never log tokens |
| `--verify` | Phase 2 (checksums) | Positive flag (default: enabled); complement to `--no-verify` |
| `--list-export-formats` | Phase 7 (config) | Print all available export formats and exit |
| `BROWSER` env var | Phase 1 (auth) | `_resolve_browser` should check `os.environ.get("BROWSER")` |
| `GDRIVE_DL_*` env vars | Phase 7 (config) | Environment variable tier between config file and CLI flags |
| `description` + `starred` | Phase 2 (DriveItem), Phase 6 (metadata sidecar) | Add to DriveItem fields and API `fields` string |
| `commentCount` | Phase 2 (DriveItem), API `fields` string | Required for Phase 6 comments optimization |
| macOS birthtime | Phase 2 (timestamps) | Best-effort via `SetFile` command; document as platform-specific |
| `flow.run_console()` | Phase 1 (auth) | Air-gapped fallback when `--no-browser` + no local server possible |
| Dual-export implementation | Phase 2 (downloader), Phase 7 (config) | Two exports per file, both recorded in manifest |

### Clean Code Reminders for Implementers

- Use `DownloadStatus` enum for all status comparisons — never use raw strings like `"completed"`
- Use `DriveType` enum (not `Literal["my_drive", "shared_drive"]`) for `DriveContext.drive_type`
- Access manifest entries via methods (`manifest.all_entries()`, `manifest.get_file()`) — never `manifest.files.items()`
- Always parenthesize compound `and`/`or` conditions
- Inject `walker` and `downloader` dependencies into `DownloadRunner` for testability
