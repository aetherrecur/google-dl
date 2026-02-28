# Phase 1: Authentication + Raw API Access

**Status:** `completed`
**Estimated effort:** Day 1–2
**Depends on:** Phase 0 (project skeleton)
**Blocks:** Phase 2 (walker + download)

---

## Objective

Implement the OAuth2 authentication flow with automatic browser launch, token caching, and a post-auth smoke test that displays Drive storage metadata. After this phase, running `gdrive-dl <SOURCE>` authenticates the user and shows account info.

---

## Deliverables

### 1. `auth.py`

**Reference:** [development-plan.md §5](development-plan.md#5-authentication-module)

#### Token Lifecycle

1. If `--service-account` set → `_authenticate_service_account()`
2. Load `token.json` → check `creds.valid`
3. If expired + has refresh token → `creds.refresh(Request())` (silent, no browser)
4. If missing or refresh fails → full browser flow via `InstalledAppFlow.run_local_server()`
5. Save `creds.to_json()` to `token_file` with `0o600` permissions

#### Key Functions

```python
def build_drive_service(config: ResolvedConfig) -> Resource:
    """Authenticate and return a Drive API v3 service object."""

def _authenticate_oauth(credentials_file, token_file, browser, no_browser) -> Credentials:
    """Run OAuth2 flow: load cached → refresh → browser flow."""

def _authenticate_service_account(key_file, scopes, subject_email=None) -> Credentials:
    """Load service account credentials."""

def _resolve_browser(browser_arg) -> Optional[str]:
    """Resolve browser name for webbrowser module."""

def _scopes_sufficient(cached_scopes, required) -> bool:
    """Check if cached token has required scopes."""

def get_drive_about(service) -> dict:
    """Fetch user info and storage quota via about.get."""
```

#### Browser Selection Logic

- `None` → system default
- `"auto"` → try Chrome, fall back to default
- `"chrome"` / `"firefox"` → explicit, error if not found
- Cross-platform Chrome detection: AppleScript on macOS, PATH lookup on Linux/Windows

#### `run_local_server` Call

```python
creds = flow.run_local_server(
    port=0,                       # auto-select
    browser=browser_name,
    open_browser=not no_browser,
    timeout_seconds=180,
)
```

#### Scope Strategy

- Default: `drive.readonly` — minimum for full download
- Never request `drive` (read/write)
- On scope mismatch: delete `token_file`, force re-auth, log clear message

#### Token Storage Security

- Write with `0o600` permissions
- Default: `~/.config/gdrive-dl/token.json` (XDG-compliant)
- Never log tokens, even with `--verbose`

### 2. Post-Auth Smoke Test: Drive Storage Metadata

**Reference:** [development-plan.md §5 — Post-Auth Verification](development-plan.md#5-authentication-module)

```python
def get_drive_about(service) -> dict:
    return service.about().get(
        fields="user(displayName,emailAddress,photoLink),"
               "storageQuota(limit,usage,usageInDrive,usageInDriveTrash)"
    ).execute()
```

Display after successful auth:

```
Authenticated as: alice@company.com (Alice Chen)
Drive storage:  12.4 GB / 15.0 GB used (82.7%)
  Drive files:  10.1 GB
  Trash:         1.2 GB (recoverable)
```

Fields:
- `storageQuota.limit` — total quota in bytes (`None` for unlimited enterprise)
- `storageQuota.usage` — total bytes used across all Google services
- `storageQuota.usageInDrive` — bytes used by Drive files
- `storageQuota.usageInDriveTrash` — bytes used by trashed files

### 3. Minimal `cli.py` Extension

Extend the Phase 0 stub to accept authentication options:

```python
@click.command()
@click.argument("source")
@click.option("--credentials", default="./credentials.json")
@click.option("--token", default="./token.json")
@click.option("--service-account", default=None)
@click.option("--browser", default=None)
@click.option("--no-browser", is_flag=True, default=False)
def main(source, credentials, token, service_account, browser, no_browser):
    """gdrive-dl: Google Drive archival CLI."""
    # 1. Build Drive service (authenticate)
    # 2. Call get_drive_about() and display results
    # 3. Extract folder ID from source
    # 4. Verify source folder exists with files.get()
```

### 4. Source ID Extraction

```python
def extract_folder_id(source: str) -> str:
    """Extract folder ID from URL, raw ID, or 'root' keyword."""
    # Handles:
    #   "root" → "root"
    #   "1ABC123xyz" → "1ABC123xyz"
    #   "https://drive.google.com/drive/folders/1ABC123xyz" → "1ABC123xyz"
    #   "https://drive.google.com/drive/folders/1ABC123xyz?usp=sharing" → "1ABC123xyz"
```

---

## Tests (Write First)

### `test_auth.py`

```python
# Token lifecycle
def test_valid_cached_token_reused():
    """When token.json has valid credentials, no browser flow is triggered."""

def test_expired_token_refreshed_silently():
    """When token is expired but has refresh token, creds.refresh() is called."""

def test_missing_token_triggers_browser_flow():
    """When token.json doesn't exist, InstalledAppFlow.run_local_server() is called."""

def test_refresh_failure_triggers_browser_flow():
    """When refresh fails (revoked token), full browser flow runs."""

# Scope handling
def test_scope_mismatch_deletes_token_and_reauths():
    """When cached scopes don't include drive.readonly, token is deleted."""

def test_scopes_sufficient_returns_true_for_superset():
    """Cached scopes that are a superset of required scopes pass."""

def test_scopes_sufficient_returns_false_for_empty():
    """Empty cached scopes fail the check."""

# Service account
def test_service_account_skips_oauth():
    """When --service-account is set, OAuth flow is skipped entirely."""

def test_service_account_with_delegation():
    """Service account with subject_email calls with_subject()."""

# Browser selection
def test_resolve_browser_none_returns_none():
    """No browser arg returns None (system default)."""

def test_resolve_browser_explicit_chrome():
    """'chrome' returns 'chrome'."""

# Token storage
def test_token_saved_with_restricted_permissions():
    """Token file is written with 0o600 permissions."""

# Drive about
def test_get_drive_about_returns_user_and_quota():
    """get_drive_about() returns user email and storage quota."""

def test_get_drive_about_handles_unlimited_quota():
    """When storageQuota.limit is None (enterprise), display 'unlimited'."""

# Source extraction
def test_extract_folder_id_from_url():
    """Full Drive URL extracts the folder ID."""

def test_extract_folder_id_from_raw_id():
    """Raw ID string is returned as-is."""

def test_extract_folder_id_from_root():
    """'root' keyword is returned as 'root'."""

def test_extract_folder_id_strips_query_params():
    """URL with ?usp=sharing query params extracts clean ID."""
```

---

## Verification Checklist

- [ ] `gdrive-dl <SOURCE>` prompts for OAuth in browser
- [ ] After auth, user email and storage quota are displayed
- [ ] Token is cached in `token.json` with `0o600` permissions
- [ ] Subsequent runs reuse cached token (no browser launch)
- [ ] `--no-browser` prints URL instead of opening browser
- [ ] `--service-account` path works with valid key file
- [ ] Invalid source URL/ID raises clear error
- [ ] `pytest tests/test_auth.py` — all tests pass
- [ ] `ruff check src/gdrive_dl/auth.py` — clean
- [ ] `mypy src/gdrive_dl/auth.py` — clean

---

## Error Handling

| Error | Response |
|-------|----------|
| `credentials.json` not found | `AuthError` → clear message with setup instructions |
| User denies OAuth consent | `AuthError` → "Authorization denied" |
| Token refresh fails | Delete token, retry browser flow |
| `about.get` fails | `AuthError` → "Authentication succeeded but API access failed" |
| Invalid source URL | `SourceNotFoundError` → "Could not extract folder ID" |
| Source folder doesn't exist | `SourceNotFoundError` → "Folder not found or not accessible" |
