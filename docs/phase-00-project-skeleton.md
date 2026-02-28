# Phase 0: Project Skeleton

**Status:** `completed`
**Estimated effort:** 1–2 hours
**Depends on:** Nothing
**Blocks:** All subsequent phases

---

## Objective

Set up the project structure, build system, and foundational leaf modules so that `pip install -e ".[dev]"` works and the `gdrive-dl` entry point resolves.

---

## Deliverables

### 1. Directory Structure

Create the src-layout structure:

```
google-dl/
├── src/
│   └── gdrive_dl/
│       ├── __init__.py
│       ├── exceptions.py
│       └── constants.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_exceptions.py
│   └── test_constants.py
├── docs/                    # already exists
├── pyproject.toml
├── .gitignore
└── LICENSE
```

### 2. `pyproject.toml`

As specified in [development-plan.md §2](development-plan.md#2-project-scaffolding):

- Build backend: `hatchling`
- Entry point: `gdrive-dl = "gdrive_dl.cli:main"`
- Dependencies: click, google-api-python-client, google-auth, google-auth-oauthlib, google-auth-httplib2, PyYAML, rich, requests
- Dev dependencies: pytest, pytest-cov, pytest-mock, ruff, mypy, type stubs
- Ruff config: line-length 100, target py39
- Mypy config: strict mode
- Pytest config: testpaths = ["tests"], coverage reporting

### 3. `__init__.py`

```python
"""gdrive-dl: Google Drive archival CLI."""
__version__ = "0.1.0"
```

### 4. `exceptions.py`

Full exception hierarchy:

```python
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

### 5. `constants.py`

- `FOLDER_MIME = "application/vnd.google-apps.folder"`
- `SHORTCUT_MIME = "application/vnd.google-apps.shortcut"`
- `SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]`
- `EXPORT_FORMATS` dict (Google MIME → (export MIME, extension))
- `NON_DOWNLOADABLE` set
- `WORKSPACE_PREFIXES`
- `DEFAULT_PAGE_SIZE = 1000`
- `DEFAULT_RETRIES = 5`
- `DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024`

### 6. `.gitignore`

As specified in [development-plan.md §2](development-plan.md#2-project-scaffolding). Must exclude:
- OAuth credentials (`credentials.json`, `token.json`, `service-account*.json`)
- Runtime artifacts (`gdrive-dl-manifest.json`, `gdrive-dl-report.*`)
- Python artifacts (`__pycache__/`, `*.egg-info/`, `dist/`, `build/`)
- Tooling caches (`.pytest_cache/`, `.coverage`, `.mypy_cache/`, `.ruff_cache/`)

### 7. `LICENSE`

MIT license.

### 8. Minimal `cli.py` stub

A placeholder so the entry point resolves:

```python
import click

@click.command()
def main():
    """gdrive-dl: Google Drive archival CLI."""
    click.echo("gdrive-dl v0.1.0 — not yet implemented")
```

---

## Tests (Write First)

### `test_exceptions.py`

```python
def test_gdrive_error_is_base():
    """All custom exceptions inherit from GdriveError."""

def test_download_error_stores_file_context():
    """DownloadError captures file_id, name, and reason."""

def test_exception_hierarchy():
    """Each exception is an instance of GdriveError."""
```

### `test_constants.py`

```python
def test_export_formats_cover_all_workspace_types():
    """EXPORT_FORMATS has entries for docs, sheets, slides, drawings, script."""

def test_non_downloadable_types():
    """NON_DOWNLOADABLE contains forms, sites, maps, fusiontable, folder, shortcut."""

def test_scopes_readonly():
    """SCOPES list contains only drive.readonly."""

def test_folder_mime_constant():
    """FOLDER_MIME matches the Google Drive folder MIME type."""
```

### `conftest.py`

Initial shared fixtures:

```python
@pytest.fixture
def tmp_output_dir(tmp_path):
    """Temporary directory for download output."""

@pytest.fixture
def sample_drive_item():
    """A representative DriveItem for testing."""
```

---

## Verification Checklist

- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `gdrive-dl --help` prints usage
- [ ] `pytest` runs and all tests pass
- [ ] `ruff check src/ tests/` passes with no errors
- [ ] `mypy src/gdrive_dl/` passes in strict mode
- [ ] All exceptions are importable: `from gdrive_dl.exceptions import AuthError`
- [ ] All constants are importable: `from gdrive_dl.constants import EXPORT_FORMATS`
- [ ] `.gitignore` excludes `credentials.json`, `token.json`

---

## Coding Standards Reminder

- Follow [python-clean-code.md](python-clean-code.md) conventions
- Guard clauses over deep nesting
- Explicit parentheses in conditionals
- Constants in `UPPER_SNAKE_CASE`
- Docstrings on all public classes and functions
