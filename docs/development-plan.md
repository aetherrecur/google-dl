# gdrive-dl: Consolidated Development Plan

A comprehensive development plan consolidating research findings across architecture, API integration, and feature design. This document is the single source of truth for implementation decisions.

---

## Table of Contents

1. [Research Summary](#1-research-summary)
2. [Project Scaffolding](#2-project-scaffolding)
3. [CLI Design](#3-cli-design)
4. [Core Module Architecture](#4-core-module-architecture)
5. [Authentication Module](#5-authentication-module)
6. [Directory Walker](#6-directory-walker)
7. [Download Engine](#7-download-engine)
8. [Rate Limiting & Resilience](#8-rate-limiting--resilience)
9. [Archival Features](#9-archival-features)
10. [Filtering](#10-filtering)
11. [Manifest & Resume](#11-manifest--resume)
12. [Timestamps & Checksums](#12-timestamps--checksums)
13. [Reporting](#13-reporting)
14. [Configuration](#14-configuration)
15. [Implementation Phases](#15-implementation-phases)
16. [Key Decisions Summary](#16-key-decisions-summary)
17. [References](#17-references)

---

## 1. Research Summary

### Sources Consulted

**Web research (Feb 2026):**
- `google-auth-oauthlib` 1.3.0 (released Feb 27, 2026) — PKCE enabled by default
- Click vs Typer vs argparse analysis for CLI framework selection
- src-layout vs flat-layout (PyPA packaging guide)
- Google Drive API v3 — permissions, revisions, and comments resources
- `MediaIoBaseDownload` chunk size benchmarks and limitations
- Atomic file write patterns for manifest safety
- Predicate pushdown patterns for two-tier filtering
- XDG config file discovery conventions

**Existing project docs:**
- `docs/oauth-browser-launch.md` — browser detection, `webbrowser` module internals
- `docs/drive-download-api.md` — API traversal, download mechanics, rate limits
- `docs/product-spec.md` — full feature spec, CLI interface, archival features
- `docs/python-clean-code.md` — coding standards and patterns

---

## 2. Project Scaffolding

### Directory Structure: src-layout

**Recommendation: src-layout.** The flat-layout has a failure mode where `sys.path[0]` (CWD) picks up the local package instead of the installed one during testing. The src-layout prevents accidental uninstalled imports entirely. This is the PyPA-recommended layout for distributed CLI tools.

```
google-dl/                          # repo root
├── src/
│   └── gdrive_dl/                  # importable package (underscore, not hyphen)
│       ├── __init__.py
│       ├── cli.py                  # Click entry point
│       ├── config.py               # YAML config loading + merge logic
│       ├── auth.py                 # OAuth2/service-account flows
│       ├── walker.py               # Drive tree traversal + metadata collection
│       ├── downloader.py           # File download + Workspace export
│       ├── filters.py              # Two-tier filtering (API query + post-fetch)
│       ├── manifest.py             # Manifest read/write, resume logic
│       ├── archival.py             # Permissions, comments, revisions extraction
│       ├── report.py               # Post-download + dry-run report generation
│       ├── timestamps.py           # mtime/ctime preservation on local files
│       ├── checksums.py            # MD5/SHA-256 verification
│       ├── throttle.py             # Rate limiting + exponential backoff
│       ├── exceptions.py           # Custom exception hierarchy
│       └── constants.py            # Enums, MIME type mappings, defaults
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # pytest fixtures (mock Drive API, temp dirs)
│   ├── test_auth.py
│   ├── test_walker.py
│   ├── test_downloader.py
│   ├── test_filters.py
│   ├── test_manifest.py
│   ├── test_config.py
│   └── test_cli.py                 # CLI integration tests via click.testing.CliRunner
├── docs/
│   ├── product-spec.md
│   ├── oauth-browser-launch.md
│   ├── drive-download-api.md
│   ├── python-clean-code.md
│   └── development-plan.md         # this document
├── pyproject.toml
├── .gitignore
├── LICENSE
└── README.md
```

### pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "gdrive-dl"
version = "0.1.0"
description = "Google Drive archival CLI — downloads files, permissions, comments, and revision history"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.9"
keywords = ["google-drive", "archive", "backup", "cli", "download"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Topic :: System :: Archiving :: Backup",
]

dependencies = [
    "click>=8.1",
    "google-api-python-client>=2.100",
    "google-auth>=2.20",
    "google-auth-oauthlib>=1.1",
    "google-auth-httplib2>=0.2",
    "PyYAML>=6.0",
    "rich>=13.0",
    "requests>=2.31",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-cov>=4.1",
    "pytest-mock>=3.11",
    "ruff>=0.1",
    "mypy>=1.5",
    "types-PyYAML>=6.0",
    "types-requests>=2.31",
]

[project.scripts]
gdrive-dl = "gdrive_dl.cli:main"

[project.urls]
Repository = "https://github.com/yourname/gdrive-dl"

[tool.hatch.build.targets.wheel]
packages = ["src/gdrive_dl"]

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "C4"]

[tool.mypy]
python_version = "3.9"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=gdrive_dl --cov-report=term-missing"
```

**Why hatchling?** Modern PyPA-endorsed build backend with the cleanest `pyproject.toml` integration. Keeps build and dependency management separate (unlike Poetry which conflates them).

**Why `rich`?** The dry-run table output and per-file progress bars are first-class features of the product spec. Rich's `Progress`, `Table`, and `Console` are purpose-built for this. The alternative (hand-rolling tqdm + tabulate) provides less value.

### `__init__.py`

Minimal — expose only version, no heavy imports at package level:

```python
"""gdrive-dl: Google Drive archival CLI."""
__version__ = "0.1.0"
```

### .gitignore

```gitignore
# Google OAuth credentials — NEVER commit
credentials.json
token.json
service-account*.json

# Runtime artifacts
gdrive-dl-manifest.json
gdrive-dl-report.*

# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/

# Virtual environments
.venv/

# Testing / tooling
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/

# OS / editor
.DS_Store
.vscode/
.idea/
```

---

## 3. CLI Design

### Framework: Click 8.x

**Recommendation: Click. Not Typer, not argparse.**

Three concrete requirements from the product spec drive this choice:

1. **`--revisions [N]` — optional value on a flag.** Click handles this cleanly with `is_flag=False, flag_value=0`. Typer has poor support for this pattern. Argparse can do it with `nargs='?'` but the code is ugly.

2. **`--export-format TYPE=FORMAT` (repeatable, key=value).** Click accepts this with `type=str, multiple=True` and a callback to parse `key=value`. Typer's type system fights this pattern.

3. **`--config FILE` with `ctx.default_map` override pattern.** Click has a first-class documented pattern: an eager callback populates `ctx.default_map`, config values become new defaults, CLI flags transparently override them. Zero custom plumbing needed.

### Positional Arguments

The spec says `gdrive-dl [OPTIONS] [OUTPUT_DIR] SOURCE`. Two positionals where the first is optional creates ambiguity. Resolution: accept SOURCE as required first positional, OUTPUT_DIR as optional second positional. Also provide `-o/--output` as the explicit override (recommended for clarity):

```python
@click.argument("source")
@click.argument("output_dir", required=False, default=None)
@click.option("-o", "--output", "output_dir_opt", default=None)
```

Precedence: `-o/--output` > positional OUTPUT_DIR > `./<folder_name>/`.

### `--dry-run` Execution Flow

`dry_run=True` is threaded through all modules. The same walker and filter code runs. The downloader receives the flag and suppresses all writes, returning `DRY_RUN` status per file. The manifest is read (for resume) but never written. The archival module estimates API call counts without making the calls.

### Config File Loading

Use Click's `ctx.default_map` eager callback:

```python
def load_config_callback(ctx, param, value):
    if value is None:
        return value
    raw = yaml.safe_load(Path(value).read_text())
    ctx.default_map = _flatten_config(raw)
    return value
```

**Override precedence (highest to lowest):**
1. CLI flags explicitly passed by the user
2. Config file values (via `ctx.default_map`)
3. Click `default=` values in option decorators

---

## 4. Core Module Architecture

### Module Dependency Graph

```
cli.py
  ├── config.py          (YAML loading, option merging)
  ├── auth.py            (credential resolution, Drive service construction)
  ├── walker.py          ← throttle.py, exceptions.py, constants.py
  ├── filters.py         ← exceptions.py
  ├── downloader.py      ← checksums.py, timestamps.py, manifest.py,
  │                         throttle.py, exceptions.py, constants.py
  ├── archival.py        ← throttle.py, exceptions.py
  ├── manifest.py        ← exceptions.py
  └── report.py          (no internal deps — pure data renderer)

constants.py             (leaf node — no internal deps)
checksums.py             (leaf node)
timestamps.py            (leaf node)
throttle.py              (leaf node)
exceptions.py            (leaf node — imported by all)
```

**Key constraint:** `manifest.py`, `checksums.py`, `timestamps.py`, `throttle.py`, `constants.py`, and `exceptions.py` are all leaf nodes. Dependency flows in one direction: `cli.py` → orchestration modules → utility leaf modules. No circular imports possible.

### Key Data Structures

```python
# config.py
@dataclass(frozen=True)
class ResolvedConfig:
    """Immutable config constructed once in cli.main(), threaded everywhere."""
    source_id: str
    output_dir: str
    dry_run: bool
    flat: bool
    shared_drives: Optional[str]      # None | "include" | "list"
    credentials_file: str
    token_file: str
    service_account_file: Optional[str]
    browser: Optional[str]
    no_browser: bool
    permissions: bool
    comments: bool
    revisions: Optional[int]          # None=disabled, 0=all, N=N most recent
    metadata: bool
    api_query: Optional[str]
    post_filter: Optional[str]
    filter_confirm: bool
    export_config: ExportConfig
    resume: bool
    manifest_file: str
    verify_checksums: bool
    rate_limit: Optional[int]
    retries: int
    report: bool
    report_format: str
    quiet: bool
    verbose: bool
```

```python
# walker.py
@dataclass
class DriveItem:
    """Core transfer object passed between walker, filters, downloader, archival."""
    id: str
    name: str
    mime_type: str
    size: Optional[int]               # None for Workspace files
    md5_checksum: Optional[str]
    created_time: str                 # RFC 3339
    modified_time: str
    parents: list[str]
    drive_path: str                   # e.g. "/Legal/Q3 Report.docx"
    is_folder: bool
    can_download: bool
    is_shortcut: bool
    shortcut_target_id: Optional[str]
    shared_drive_id: Optional[str]

    @property
    def is_workspace_file(self) -> bool:
        return self.mime_type.startswith("application/vnd.google-apps.")
```

```python
# manifest.py
class DownloadStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CHECKSUM_FAILED = "checksum_failed"
    DRY_RUN = "dry_run"
```

### Data Flow

```
User runs: gdrive-dl --permissions ./backup 1ABC123xyz

cli.py: main()
  1. Config callback fires (eager) → populates ctx.default_map
  2. Click resolves all parameters
  3. Construct ResolvedConfig
  4. auth.build_drive_service(config) → Resource
  5. source_id = extract_folder_id(source)
  6. manifest = Manifest.load_or_create(config.manifest_file)
  7. runner = DownloadRunner(service, config, manifest)
  8. result = runner.run()

DownloadRunner.run():
  1. root_meta = walker.get_folder_metadata(service, source_id)
  2. file_tree = walker.walk(service, source_id, config)
  3. filtered_tree = filters.apply(file_tree, config)
  4. For each DriveItem:
     a. Check manifest for completion (resume logic)
     b. Download file (blob or Workspace export)
     c. Run archival (permissions, comments, revisions)
     d. Verify checksum, apply timestamps
     e. Update manifest
  5. manifest.save()
  6. Return DownloadResult

cli.py (post-run):
  if dry_run: print dry-run report
  if report: generate download report
```

### Error Handling Strategy

```python
# exceptions.py
class GdriveError(Exception): ...
class AuthError(GdriveError): ...
class SourceNotFoundError(GdriveError): ...
class DownloadError(GdriveError):
    def __init__(self, file_id, name, reason): ...
class ChecksumError(GdriveError): ...
class RateLimitError(GdriveError): ...
class FilterCostError(GdriveError): ...
class ManifestError(GdriveError): ...
class ConfigError(GdriveError): ...
```

**Catch vs. propagate:**

| Location | Catch | Propagate |
|----------|-------|-----------|
| `throttle.py` | `HttpError 429/403` | Never — retry internally |
| `downloader.py` per-file | `DownloadError`, `ChecksumError` | Never — log to manifest, continue |
| `archival.py` per-file | All `GdriveError` | Never — archival is best-effort |
| `auth.py` | Never | `AuthError` — fatal |
| `cli.main()` | `AuthError`, `SourceNotFoundError`, `ConfigError` | Never — convert to `click.ClickException` |

---

## 5. Authentication Module

### OAuth Flow (`auth.py`)

**Library state (Feb 2026):** `google-auth-oauthlib` 1.3.0 — PKCE enabled by default, `browser` parameter stable.

**Token lifecycle:**
1. If `--service-account` set → skip OAuth entirely
2. Load `token.json` → check `creds.valid`
3. If expired + has refresh token → `creds.refresh(Request())` (silent, no browser)
4. If missing or refresh fails → full browser flow
5. Save `creds.to_json()` to `token_file`

**Scope strategy:** Default `drive.readonly` — minimum required for full download. Never request `drive` (read/write). Detect scope mismatch on cached tokens:

```python
def _scopes_sufficient(cached_scopes, required):
    if not cached_scopes:
        return False
    return set(required).issubset(set(cached_scopes))
```

If insufficient: delete `token_file`, force re-auth, log clear message.

### Browser Selection

```python
def _resolve_browser(browser_arg):
    """Returns webbrowser-compatible name or None for system default."""
    # "auto" → try chrome, fall back to default
    # "chrome"/"firefox" → explicit, error if not found
    # None → system default
```

For `"auto"`: check `BROWSER` env var → try `webbrowser.get("chrome")` → try `find_chrome_path()` + register → fall back to `None`.

**run_local_server call:**
```python
creds = flow.run_local_server(
    port=0,                       # auto-select; never hardcode 8080
    browser=browser_name,
    open_browser=not no_browser,
    timeout_seconds=180,
)
```

### Headless / No-Browser Mode

When `--no-browser`: `open_browser=False`, library prints URL. For fully air-gapped environments, use `flow.run_console()` (code-paste flow, no local server).

### Service Account Support

```python
def _authenticate_service_account(key_file, scopes, subject_email=None):
    creds = service_account.Credentials.from_service_account_file(key_file, scopes=scopes)
    if subject_email:
        creds = creds.with_subject(subject_email)  # Domain-Wide Delegation
    return creds
```

No `token.json` produced. `--service-account` takes precedence over `--credentials`/`--token`.

### Token Storage Security

Write with owner-only permissions (`0o600`). Default location: `~/.config/gdrive-dl/token.json` (XDG-compliant). Never log tokens even with `--verbose`.

### Post-Auth Verification: Drive Storage Metadata

After successful authentication, call the `about.get` endpoint to verify credentials and display account context:

```python
def get_drive_about(service) -> dict:
    """Fetch user info and storage quota. Validates auth + scope in one call."""
    return service.about().get(
        fields="user(displayName,emailAddress,photoLink),"
               "storageQuota(limit,usage,usageInDrive,usageInDriveTrash)"
    ).execute()
```

**Fields returned by `storageQuota`:**

| Field | Description |
|---|---|
| `limit` | Total storage quota in bytes (across Gmail, Drive, Photos). `None` for unlimited (Workspace enterprise). |
| `usage` | Total bytes used across all Google services |
| `usageInDrive` | Bytes used by Drive files specifically |
| `usageInDriveTrash` | Bytes used by trashed Drive files (recoverable space) |

Display example after auth:

```
Authenticated as: alice@company.com (Alice Chen)
Drive storage:  12.4 GB / 15.0 GB used (82.7%)
  Drive files:  10.1 GB
  Trash:         1.2 GB (recoverable)
```

This serves as the Phase 1 smoke test — a single lightweight API call that confirms the OAuth token, scope, and network connectivity are all working. The storage data is also useful context before a large download (available disk space vs Drive usage).

---

## 6. Directory Walker

### Traversal Strategy

**Heuristic:**
- `folder_id == "root"` or Shared Drive root → flat-list (fewer HTTP calls for large drives)
- Specific subfolder → recursive BFS (avoids fetching irrelevant metadata)

**BFS over DFS:** avoids Python recursion limit on deep trees, predictable memory usage, easier parallelization.

```python
def walk_bfs(service, root_folder_id, extra_query=""):
    queue = deque([(root_folder_id, Path())])
    all_nodes = []
    while queue:
        folder_id, local_base = queue.popleft()
        items = _list_folder(service, folder_id, extra_query)
        for item in items:
            node = _build_node(item, local_base)
            all_nodes.append(node)
            if item["mimeType"] == FOLDER_MIME:
                queue.append((item["id"], local_base / item["name"]))
    return all_nodes
```

### API Fields

Always use the `fields` parameter — never omit it:

```
nextPageToken,
files(
  id, name, mimeType, size, quotaBytesUsed,
  createdTime, modifiedTime, parents,
  md5Checksum, sha256Checksum, trashed, driveId,
  shared, ownedByMe,
  capabilities/canDownload,
  shortcutDetails/targetId,
  shortcutDetails/targetMimeType,
  shortcutDetails/targetResourceKey,
  exportLinks
)
```

Use `pageSize=1000` (maximum) and `supportsAllDrives=True` + `includeItemsFromAllDrives=True` on every call.

### Shortcut Resolution

Shortcuts have `mimeType = "application/vnd.google-apps.shortcut"` with `shortcutDetails.targetId`. Resolution requires a separate `files.get` call per shortcut. **Cycle detection** via `visited_ids` set is mandatory — shortcuts can create circular references.

### Name Collision Handling

Google Drive allows duplicate names in the same folder; local filesystems do not. Default strategy: append `__{file_id[:8]}` suffix to duplicates. Deterministic across runs (same Drive ID → same suffix). Record original name in manifest.

### Shared Drive Detection

```python
@dataclass
class DriveContext:
    drive_type: Literal["my_drive", "shared_drive"]
    drive_id: Optional[str]

    def list_kwargs(self) -> dict:
        kwargs = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}
        if self.drive_type == "shared_drive":
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = self.drive_id
        return kwargs
```

Pass `**ctx.list_kwargs()` into every API call to centralize Shared Drive boilerplate.

---

## 7. Download Engine

### Blob File Download

Chunk size selection by file size:

| File size | Chunk size | Rationale |
|---|---|---|
| < 1 MB | Entire file | Single-chunk, no benefit to chunking |
| 1 MB – 100 MB | 5 MB | Good balance of round trips vs memory |
| 100 MB+ | 10 MB | Fewer round trips; cap here for API stability |

**Partial file safety:** write to `filename.ext.partial`, rename atomically on completion. On `--resume`, delete any `.partial` files found.

**Progress reporting:** integrate with `rich.progress`. `status.resumable_progress` gives bytes received per chunk.

### Workspace File Export

```python
EXPORT_FORMATS = {
    "application/vnd.google-apps.document":
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet":
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation":
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.script": ("application/vnd.google-apps.script+json", ".json"),
}
```

**Format selection precedence:** per-file override (from `--export-config` path match) → per-type global override (`--export-format`) → default from table above.

**Dual-export:** export both formats sequentially. Both paths recorded in manifest under same `file_id` with different `export_format` keys.

### Handling the 10MB Export Limit

`files.export` enforces a hard 10 MB limit. On `403 exportSizeLimitExceeded`:

1. Fall back to `exportLinks` — browser-style download URLs available in the file's metadata
2. These URLs bypass the 10 MB limit but require Bearer token authentication
3. Stream via `requests.get(url, headers={"Authorization": f"Bearer {creds.token}"}, stream=True)`

**Important:** `exportLinks` tokens expire with the access token (~1 hour). Proactively refresh before starting large exports.

### Non-Downloadable Types

```python
NON_DOWNLOADABLE = {
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.site",
    "application/vnd.google-apps.map",
    "application/vnd.google-apps.fusiontable",
    "application/vnd.google-apps.folder",
    "application/vnd.google-apps.shortcut",
    "application/vnd.google-apps.drive-sdk",
}
```

---

## 8. Rate Limiting & Resilience

### API Quotas

| Limit | Value |
|---|---|
| Queries per 60 seconds (project) | 12,000 (~200 req/sec) |
| File export limit | 10 MB per `files.export` call |
| Download bandwidth | ~10 GB/day (undocumented) |

### Adaptive Throttling

Token-bucket rate limiter starting at 10 req/sec, max 50 req/sec. On 429/403-rateLimit: double the interval (halve rate). On success: gradually recover (5% increase toward max). Manual override via `--rate-limit N`.

### Exponential Backoff with Full Jitter

Following Google's documented recommendation and the AWS full-jitter strategy:

```python
def _compute_backoff_delay(attempt, base_delay=1.0, max_delay=64.0):
    cap = min(max_delay, base_delay * (2 ** attempt))
    return random.uniform(0, cap)
```

Full-jitter distributes retries across the full window, preventing synchronized retry storms when multiple downloads hit rate limits simultaneously.

**Retryable status codes:** `429, 500, 502, 503, 504`. For `403`, check the reason:
- `rateLimitExceeded` / `userRateLimitExceeded` → retry with backoff
- `downloadQuotaExceeded` → NOT retryable (daily limit; save manifest, exit cleanly)
- `domainPolicy` / `cannotDownload` → NOT retryable

### Connection Error Recovery

`MediaIoBaseDownload` cannot resume partial files. On network error: delete partial file, retry from byte 0 with backoff. The `.partial` file extension pattern ensures incomplete downloads are never mistaken for complete ones.

---

## 9. Archival Features

### Permissions Snapshot (`--permissions`)

**API:** One `permissions.list` call per file/folder (no batching across files). This is the most expensive archival feature — doubles API call count for typical directories.

**Fields to capture:**
```
permissions(
    id, type, role, emailAddress, displayName, domain,
    expirationTime, allowFileDiscovery, deleted, pendingOwner,
    permissionDetails(permissionType, role, inherited, inheritedFrom)
)
```

**Inherited vs. direct:** `permissionDetails[].inherited` distinguishes direct from inherited permissions. The sidecar includes computed `summary.directPermissions` and `summary.inheritedPermissions` counts for fast auditing.

**Sidecar naming:**
- Files: `Q3 Report.docx.permissions.json`
- Folders: `reports/.folder.permissions.json`

**Optimization:** Concurrent fetching with 4-thread pool. Skip re-fetch on `--resume` if `modifiedTime` unchanged.

### Revision History (`--revisions [N]`)

**API:** `revisions.list` (1 call per file) + per-revision download.

**Critical constraint with `drive.readonly` scope:** Blob file revisions can only be downloaded if `keepForever=true` (marking them requires write scope). Workspace revisions are accessible via `exportLinks` without write scope.

**Strategy:**
- Blob files: download only revisions already marked `keepForever`
- Workspace files: export via per-revision `exportLinks`
- Document this limitation prominently

**Naming:** `{modifiedTime_safe}_{revisionId}_{originalName}` in a `.revisions/` subdirectory.

**`--revisions N`:** Sort chronologically, take last N: `revisions[-N:]`.

**File type support:**

| Type | revisions.list | Blob download | Export via exportLinks |
|---|---|---|---|
| Blob files (PDF, image) | Yes | Yes, if `keepForever` | N/A |
| Google Docs | Yes (may be incomplete) | No | Yes |
| Google Sheets | Yes (may be incomplete) | No | Yes |
| Google Slides | Yes (may be incomplete) | No | Yes |
| Google Forms | Yes | No | No |

### Comments Preservation (`--comments`)

**API:** `comments.list` with replies included inline via `fields` parameter. One call per file that has comments. The `fields` parameter is **mandatory** — the API returns nothing without it.

**Optimization:** Include `commentCount` in walker fields. If `commentCount == 0`, skip the `comments.list` call entirely.

**Anchored comments:** The `anchor` field is an opaque JSON string describing the document region. Parse best-effort into `anchorParsed`; store raw string verbatim as source of truth. Anchor positions reference internal revision IDs and cannot be mapped to exported file positions — this is a fundamental limitation.

**Sidecar:** `Q3 Report.docx.comments.json` with full comment threads, resolved status, and parsed anchors.

---

## 10. Filtering

### Two-Tier Architecture

**Tier 1 — API pushdown (`--query`):** Injected verbatim into the `q` parameter of `files.list`. Fast — reduces data fetched from the API. No extra calls.

```python
def build_query(folder_id, extra_query=None):
    base = f"'{folder_id}' in parents and trashed = false"
    if extra_query:
        return f"({base}) and ({extra_query})"
    return base
```

**Tier 2 — Post-fetch (`--filter`):** Applied locally after metadata retrieval. Some predicates require additional API calls.

**Supported filter predicates:**

| Expression | Cost | Extra API calls |
|---|---|---|
| `size>10mb` | Free | None |
| `ext:.pdf` | Free | None |
| `name:report` | Free | None |
| `modified_before:2025-01-01` | Free | None |
| `owner:alice@company.com` | Free | None (owner in walker metadata) |
| `shared_by:alice@company.com` | Per-file | +1 permissions.list |
| `has:comments` | Free/Per-file | None if `commentCount` available |
| `has:revisions` | Per-file | +1 revisions.list |

**Evaluation order:** Free predicates first (short-circuit before expensive ones).

### `--filter-confirm` Safety

If estimated extra API calls > 100 and `--filter-confirm` not set and not `--dry-run`: print cost warning and exit. In `--dry-run` mode, show cost estimate without prompting.

### Dry-Run Interaction

Free predicates are evaluated. Per-file predicates report files as "conditionally included" — the dry-run report shows how many files would require API evaluation.

---

## 11. Manifest & Resume

### Manifest JSON Schema

```json
{
  "schemaVersion": 1,
  "sessionId": "uuid4",
  "createdAt": "RFC3339",
  "updatedAt": "RFC3339",
  "source": { "folderId": "...", "folderName": "...", "driveId": null },
  "options": { "outputDir": "...", "flat": false, "permissions": true, ... },
  "stats": {
    "totalDiscovered": 312,
    "totalCompleted": 287,
    "totalSkipped": 18,
    "totalFailed": 7,
    "totalBytesDownloaded": 1820000000,
    "apiCallsMade": 720
  },
  "files": {
    "<fileId>": {
      "fileId": "...",
      "name": "...",
      "localPath": "...",
      "driveModifiedTime": "...",
      "driveMd5Checksum": "...",
      "status": "completed|pending|failed|skipped|in_progress|checksum_failed",
      "errorMessage": null,
      "retryCount": 0,
      "sidecars": { "permissions": "...", "comments": null, "revisions": null }
    }
  }
}
```

**Keyed by `fileId`**, not local path — enables resume even if output directory moves.

### Write Strategy: Incremental Atomic Flushes

- In-memory updates on every status change
- Atomic flush to disk every 10 completions or every 30 seconds (whichever first)
- Always flush on clean exit, SIGTERM/SIGINT
- Atomic write pattern: `tempfile.mkstemp()` → `json.dump()` → `os.fsync()` → `os.replace()`

### Resume Logic (`--resume`)

1. Load manifest → validate schema version
2. Walk Drive tree again (files may have changed)
3. Diff manifest vs current Drive state:
   - `completed` + same `modifiedTime` → **skip**
   - `completed` + different `modifiedTime` → **re-queue** (file changed)
   - `failed` / `in_progress` → **re-queue**
   - `pending` → **queue**
   - New file in Drive → **queue as new**
   - File in manifest but deleted from Drive → mark `skipped`
4. Download only queued files

### Corruption Handling

On `json.JSONDecodeError`: print clear error, suggest running without `--resume`, exit code 2. Never attempt to partially load a corrupt manifest.

---

## 12. Timestamps & Checksums

### Timestamp Preservation (`timestamps.py`)

- `mtime`: always set via `os.utime()` — reliable on all platforms
- `atime`: set to `createdTime` if available, else `modifiedTime`
- macOS birthtime: best-effort via `SetFile` command (Xcode CLI Tools)
- Apply timestamps **after** file is fully written and checksum-verified
- Apply directory timestamps bottom-up (leaves before parents) so child file creation doesn't update parent `mtime`

### MD5 Verification (`checksums.py`)

Only blob files have `md5Checksum` (Workspace exports have none). Also request `sha256Checksum` when available (newer API responses).

**Mismatch strategy (3 outcomes):**
1. **Retry** (up to 2 re-downloads): delete corrupt file, re-download
2. **Warn** (after retries exhausted): keep file, flag in manifest
3. **Fail**: delete file, mark failed in manifest

---

## 13. Reporting

### Statistics Collection

A `SessionStats` dataclass accumulates throughout the download, updated after each file:

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
    failed_files: list[FileResult]
    non_downloadable_items: list[dict]
```

### Dry-Run Report

Shows: file counts by category, estimated download size, estimated API calls (broken down by operation), predicted time, quota headroom, non-downloadable items, filter effects.

### Post-Download Report

Shows: session metadata, result counts, bytes downloaded, checksum verification summary, API call breakdown, failed files with error reasons, skipped files with skip reasons.

### Output Formats

- **Markdown** (default): human-readable, suitable for archiving alongside downloads
- **HTML**: self-contained page with inline CSS, readable in any browser offline
- **JSON**: machine-readable, suitable for downstream tooling

---

## 14. Configuration

### YAML Config Schema

```yaml
credentials: ./credentials.json
token: ./token.json
browser: null
verify: true
retries: 5
rate_limit: null

archival:
  permissions: false
  comments: false
  revisions: false          # false | true (all) | integer (N most recent)
  metadata: false

export_formats:
  defaults:
    docs: docx
    sheets: xlsx
    slides: pptx
  overrides:
    "/Legal":
      docs: pdf
      sheets: pdf

report: false
report_format: markdown
```

### Config File Discovery

Search order (first found wins):
1. `--config FILE` (explicit, hard error if missing)
2. `./gdrive-dl.yaml` / `./gdrive-dl.yml`
3. `$XDG_CONFIG_HOME/gdrive-dl/config.yaml`
4. `~/.config/gdrive-dl/config.yaml`
5. `~/.gdrive-dl.yaml`
6. Platform-specific: `~/Library/Application Support/gdrive-dl/config.yaml` (macOS), `%APPDATA%\gdrive-dl\config.yaml` (Windows)

### Merge Precedence

Lowest to highest: config file → environment variables (`GDRIVE_DL_*` prefix) → CLI flags.

**Critical detail:** CLI defaults from Click must not silently override config file values. Only explicitly-provided CLI args override config — this is handled by Click's `ctx.default_map` mechanism.

---

## 15. Implementation Phases

### Phase 0: Project Skeleton (1–2 hours)

- `pyproject.toml`, `src/gdrive_dl/__init__.py`
- `exceptions.py` (full hierarchy), `constants.py` (MIME maps, scopes)
- `.gitignore`
- `pip install -e ".[dev]"` — verify entry point resolves

### Phase 1: Auth + Raw API Access (Day 1–2)

- `auth.py` — OAuth2 flow with auto-launch browser, token caching, browser/no-browser modes
- Minimal `cli.py` with SOURCE argument and auth options
- Post-auth smoke test: call `about.get(fields="user,storageQuota")` and display:
  - Authenticated user email and display name
  - Total storage quota, used storage, Drive usage, trash usage
  - This validates auth + scopes are working and gives the user immediate feedback
- The `about.get` call also serves as the basis for quota headroom reporting in later phases

### Phase 2: Walker + Basic Download (Day 3–5)

- `walker.py` — BFS traversal with pagination, yields `DriveItem`
- `downloader.py` — blob download (streaming), Workspace export (single format)
- `timestamps.py`, `checksums.py`, `manifest.py` (basic read/write)
- `DownloadRunner` orchestrator
- Rich progress bar
- **v0.1 milestone:** `gdrive-dl 1ABC123xyz` downloads a folder tree

### Phase 3: Throttle + Robustness (Day 6–7)

- `throttle.py` — token-bucket rate limiter, exponential backoff with jitter
- Wrap every API call through throttler
- `--retries`, `--rate-limit` CLI options

### Phase 4: Filtering (Day 8–9)

- `filters.py` — API query pass-through, post-fetch filter engine
- `--filter-confirm` cost guard
- Integration with walker (API query) and DownloadRunner (post-fetch)

### Phase 5: Dry-Run Report (Day 10)

- `DryRunReporter` in `report.py` — Rich table output
- API call estimation logic

### Phase 6: Archival Features (Day 11–14)

Independent of each other; can be parallelized:
1. `archival.save_permissions()` — `permissions.list` API + sidecar
2. `archival.save_comments()` — `comments.list` API + sidecar
3. `archival.save_metadata()` — serialize `DriveItem` fields to sidecar
4. `archival.save_revisions()` — `revisions.list` + per-revision download

Implement permissions and comments first (simpler), revisions last (most complex).

### Phase 7: Config File + Export Config (Day 15–16)

- `config.py` — YAML loading, `_flatten_config()`, `ExportConfig`
- `load_config_callback` in `cli.py`
- Per-directory export format overrides

### Phase 8: Report Generation (Day 17)

- `ReportGenerator` — Markdown, HTML, JSON output
- Wire `--report` and `--report-format`

### Phase 9: Shared Drives (Day 18)

- `DriveContext` with `supportsAllDrives` on all calls
- `--shared-drives=list` interactive selector
- Auto-discovery via `drives.list`

### Phase 10: Polish + Resume (Day 19–20)

- Full manifest-based resume with diff logic
- Incremental re-run (compare `modifiedTime` / `md5Checksum`)
- `--no-verify`, checksum skip
- Final CLI help text review

### Minimum Viable v0.1

Phases 0–3 only:
- OAuth authentication (browser + no-browser)
- Recursive folder download preserving directory structure
- Workspace export (default formats)
- MD5 verification
- Basic manifest (resumable downloads)
- Rate limiting and retry
- Rich progress bar

### Parallel Development Opportunities

Once Phases 0–2 are complete, these are fully independent:

| Feature | Depends On | Blocks |
|---|---|---|
| `filters.py` | walker.py | Nothing |
| `archival.save_permissions` | auth, DriveItem | Nothing |
| `archival.save_comments` | auth, DriveItem | Nothing |
| `archival.save_metadata` | DriveItem only | Nothing |
| `config.py` YAML loading | ResolvedConfig | cli.py callback |
| Dry-run report | DownloadResult | Nothing |
| Report generation | DownloadResult | Nothing |

---

## 16. Key Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| Project layout | src-layout | Prevents accidental uninstalled import; PyPA recommended |
| Build backend | hatchling | Modern, minimal pyproject.toml; PyPA endorsed |
| CLI framework | Click 8.x | Best support for optional-value flags, `ctx.default_map`, repeatable key=value options |
| Progress/output | Rich | First-class tables, progress bars, styled output |
| Google API client | google-api-python-client + google-auth-oauthlib | Official Google libraries |
| Config override | Click `ctx.default_map` eager callback | Automatic type conversion; zero custom merge logic |
| `--revisions [N]` | `is_flag=False, flag_value=0` | `None`=disabled, `0`=all, `N`=N most recent |
| Traversal | BFS (not DFS recursion) | Avoids recursion limit; predictable memory |
| Traversal scope | Recursive for subfolders, flat-list for root | Minimize HTTP calls proportional to target |
| Chunk size | 5 MB default, 10 MB for 100MB+ files | Balance round trips vs memory |
| Partial files | `.partial` extension + atomic rename | Prevents incomplete files being treated as complete |
| Workspace >10MB | `exportLinks` fallback | Bypasses `files.export` 10 MB limit |
| Rate limiting | Adaptive throttle + full-jitter backoff | Follows Google's guidelines; handles thundering herd |
| Manifest writes | Atomic temp+rename every 10 files or 30s | Prevents corruption on crash |
| Manifest key | fileId (not local path) | Resume works even if output dir moves |
| Revision scope | `drive.readonly` — blob only if `keepForever` | Avoids requiring write scope |
| Error strategy | Custom hierarchy; catch at recovery boundary | Per-file non-fatal; auth/source fatal |
| Shared Drive | `DriveContext` dataclass on every call | Centralizes boilerplate; prevents 404 errors |

---

## 17. References

### Google Drive API
- [Files Resource (v3)](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)
- [Permissions Resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/permissions)
- [Revisions Resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/revisions)
- [Comments Resource](https://developers.google.com/workspace/drive/api/reference/rest/v3/comments)
- [Download & Export Files](https://developers.google.com/workspace/drive/api/guides/manage-downloads)
- [Manage Revisions](https://developers.google.com/workspace/drive/api/guides/manage-revisions)
- [Manage Comments](https://developers.google.com/workspace/drive/api/guides/manage-comments)
- [Export MIME Types](https://developers.google.com/workspace/drive/api/guides/ref-export-formats)
- [Search Query Reference](https://developers.google.com/workspace/drive/api/guides/ref-search-terms)
- [Usage Limits](https://developers.google.com/workspace/drive/api/guides/limits)
- [Shared Drives Guide](https://developers.google.com/workspace/drive/api/guides/about-shareddrives)
- [Python Quickstart](https://developers.google.com/workspace/drive/api/quickstart/python)

### Python Ecosystem
- [Click Options Documentation (8.3.x)](https://click.palletsprojects.com/en/stable/options/)
- [Click Config Files Pattern](https://jwodder.github.io/kbits/posts/click-config/)
- [src-layout vs flat-layout (PyPA)](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [Writing pyproject.toml (PyPA)](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
- [google-api-python-client](https://github.com/googleapis/google-api-python-client)
- [google-auth-oauthlib](https://google-auth-oauthlib.readthedocs.io/)

### Patterns & Best Practices
- [Exponential Backoff and Jitter (AWS)](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- [Atomic File Write Pattern](https://gist.github.com/therightstuff/cbdcbef4010c20acc70d2175a91a321f)
- [Predicate Pushdown (Polars)](https://pola.rs/posts/predicate-pushdown-query-optimizer/)
- [XDG Config Discovery](https://confuse.readthedocs.io/en/latest/usage.html)
