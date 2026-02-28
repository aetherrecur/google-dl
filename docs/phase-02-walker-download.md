# Phase 2: Walker + Basic Download

**Status:** `pending`
**Estimated effort:** Day 3–5
**Depends on:** Phase 1 (auth)
**Blocks:** Phase 3 (throttle), Phase 4–10 (all subsequent)

---

## Objective

Implement BFS directory traversal, blob file download, Workspace export, checksum verification, timestamp preservation, basic manifest, and Rich progress bar. After this phase, `gdrive-dl <FOLDER_ID>` downloads a complete folder tree to disk.

**v0.1 milestone:** This is the core download functionality.

---

## Deliverables

### 1. `walker.py` — Directory Traversal

**Reference:** [development-plan.md §6](development-plan.md#6-directory-walker)

#### Key Functions

```python
def walk(service, root_folder_id, config) -> list[DriveItem]:
    """BFS traversal of Drive folder tree. Returns flat list of DriveItems."""

def get_folder_metadata(service, folder_id) -> dict:
    """Fetch metadata for the root folder (name, driveId)."""
```

#### `DriveItem` Dataclass

```python
@dataclass
class DriveItem:
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

#### BFS Traversal

```python
def _walk_bfs(service, root_folder_id, extra_query=""):
    queue = deque([(root_folder_id, Path())])
    all_nodes = []
    visited_ids = set()  # cycle detection for shortcuts
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

#### API Fields

Always specify `fields` parameter:
```
nextPageToken,files(id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,
parents,md5Checksum,sha256Checksum,trashed,driveId,shared,ownedByMe,
capabilities/canDownload,shortcutDetails/targetId,shortcutDetails/targetMimeType,
shortcutDetails/targetResourceKey,exportLinks)
```

Use `pageSize=1000`, `supportsAllDrives=True`, `includeItemsFromAllDrives=True`.

#### Shortcut Resolution

- Detect via `mimeType == "application/vnd.google-apps.shortcut"`
- Resolve with `files.get(shortcutDetails.targetId)`
- Track `visited_ids` to prevent infinite loops from circular shortcuts

#### Name Collision Handling

- Detect duplicate names in same folder
- Append `__{file_id[:8]}` suffix to duplicates
- Record original name in manifest

### 2. `downloader.py` — File Download

**Reference:** [development-plan.md §7](development-plan.md#7-download-engine)

#### Key Functions

```python
def download_file(service, item: DriveItem, local_path: Path, config) -> DownloadResult:
    """Download a single file (blob or Workspace export)."""

def _download_blob(service, file_id, dest_path, file_size) -> int:
    """Stream blob file via MediaIoBaseDownload."""

def _export_workspace(service, item: DriveItem, dest_path, export_mime, creds) -> int:
    """Export Workspace file. Falls back to exportLinks for >10MB."""
```

#### Chunk Size Selection

| File size | Chunk size |
|-----------|-----------|
| < 1 MB | Entire file (single request) |
| 1–100 MB | 5 MB |
| 100 MB+ | 10 MB |

#### Partial File Safety

- Write to `filename.ext.partial`
- Atomic rename (`os.replace`) on completion
- On `--resume`, delete orphaned `.partial` files

#### Workspace Export

- Use `EXPORT_FORMATS` from `constants.py` for default MIME → extension mapping
- On `403 exportSizeLimitExceeded` (>10 MB): fall back to `exportLinks` URLs
- `exportLinks` require Bearer token auth via `requests.get(url, headers=..., stream=True)`
- Proactively refresh token before large exports

#### Non-Downloadable Types

Skip files in `NON_DOWNLOADABLE` set. Log as `SKIPPED` in manifest with reason.

### 3. `checksums.py` — MD5 Verification

**Reference:** [development-plan.md §12](development-plan.md#12-timestamps--checksums)

```python
def verify_checksum(file_path: Path, expected_md5: Optional[str]) -> bool:
    """Verify MD5 checksum. Returns True if match or no checksum available."""
```

- Only blob files have `md5Checksum` (Workspace exports have none → always pass)
- On mismatch: retry download (up to 2 re-downloads), then warn/fail
- Also check `sha256Checksum` when available

### 4. `timestamps.py` — Timestamp Preservation

**Reference:** [development-plan.md §12](development-plan.md#12-timestamps--checksums)

```python
def apply_timestamps(file_path: Path, modified_time: str, created_time: str):
    """Set mtime and atime from Drive timestamps."""
```

- `mtime` → `os.utime()` with `modifiedTime`
- `atime` → `createdTime` if available, else `modifiedTime`
- Apply **after** file is fully written and checksum-verified
- Apply directory timestamps bottom-up (leaves before parents)

### 5. `manifest.py` — Basic Manifest

**Reference:** [development-plan.md §11](development-plan.md#11-manifest--resume)

```python
class Manifest:
    def load_or_create(cls, path: str) -> "Manifest": ...
    def update_file(self, file_id: str, status: DownloadStatus, **kwargs): ...
    def save(self): ...
    def is_completed(self, file_id: str) -> bool: ...
```

#### Write Strategy

- In-memory updates on every status change
- Atomic flush every 10 completions or 30 seconds
- Always flush on clean exit and SIGTERM/SIGINT
- Atomic write: `tempfile.mkstemp()` → `json.dump()` → `os.fsync()` → `os.replace()`

### 6. `DownloadRunner` Orchestrator

Coordinates walker → download → checksum → timestamp → manifest:

```python
class DownloadRunner:
    def __init__(self, service, config, manifest): ...

    def run(self) -> DownloadResult:
        root_meta = walker.get_folder_metadata(...)
        file_tree = walker.walk(...)
        for item in file_tree:
            if manifest.is_completed(item.id):
                continue
            result = downloader.download_file(...)
            checksums.verify_checksum(...)
            timestamps.apply_timestamps(...)
            manifest.update_file(...)
        manifest.save()
        return DownloadResult(...)
```

### 7. Rich Progress Bar

Integrate `rich.progress.Progress` for:
- Overall progress: `[X/Y files] [progress bar] [bytes downloaded]`
- Per-file progress: show current file name and download percentage
- Use `status.resumable_progress` from `MediaIoBaseDownload` for byte-level tracking

---

## Tests (Write First)

### `test_walker.py`

```python
def test_walk_single_folder():
    """Walk a folder with 3 files returns 3 DriveItems."""

def test_walk_nested_folders():
    """BFS traversal of nested folders builds correct drive_path."""

def test_walk_pagination():
    """When API returns nextPageToken, fetches subsequent pages."""

def test_walk_shortcut_resolution():
    """Shortcuts resolve to target file with separate files.get call."""

def test_walk_shortcut_cycle_detection():
    """Circular shortcut references don't cause infinite loop."""

def test_walk_name_collision():
    """Duplicate names in same folder get __<id[:8]> suffix."""

def test_walk_shared_drive_kwargs():
    """Shared Drive items include supportsAllDrives in API calls."""

def test_build_drive_item():
    """API response is correctly mapped to DriveItem dataclass."""

def test_workspace_file_detection():
    """is_workspace_file returns True for Google Docs MIME types."""
```

### `test_downloader.py`

```python
def test_download_blob_small_file():
    """Files <1MB download in single chunk."""

def test_download_blob_large_file():
    """Files >100MB use 10MB chunk size."""

def test_partial_file_renamed_on_completion():
    """Download writes .partial, renames on success."""

def test_partial_file_deleted_on_failure():
    """Failed download leaves no .partial file."""

def test_export_workspace_doc_to_docx():
    """Google Doc exports to .docx with correct MIME type."""

def test_export_workspace_fallback_export_links():
    """On exportSizeLimitExceeded, falls back to exportLinks."""

def test_non_downloadable_skipped():
    """Files in NON_DOWNLOADABLE set are skipped with SKIPPED status."""
```

### `test_checksums.py`

```python
def test_md5_match():
    """Matching MD5 returns True."""

def test_md5_mismatch():
    """Non-matching MD5 returns False."""

def test_no_checksum_available():
    """When expected_md5 is None (Workspace file), returns True."""
```

### `test_timestamps.py`

```python
def test_mtime_set_from_modified_time():
    """File mtime matches Drive modifiedTime after apply_timestamps."""

def test_atime_set_from_created_time():
    """File atime matches Drive createdTime after apply_timestamps."""

def test_directory_timestamps_bottom_up():
    """Parent directory mtime is set after child files."""
```

### `test_manifest.py`

```python
def test_create_new_manifest():
    """New manifest has empty files dict and schema version 1."""

def test_load_existing_manifest():
    """Loading existing manifest preserves file entries."""

def test_update_file_status():
    """update_file changes status and updates timestamp."""

def test_is_completed():
    """is_completed returns True only for COMPLETED status."""

def test_atomic_write():
    """Manifest write uses temp file + rename pattern."""

def test_corrupt_manifest_raises_error():
    """Invalid JSON in manifest file raises ManifestError."""
```

---

## Verification Checklist

- [ ] `gdrive-dl <FOLDER_URL>` downloads all files preserving directory structure
- [ ] Workspace files export to correct default formats (.docx, .xlsx, .pptx)
- [ ] Large Workspace files (>10MB) fall back to `exportLinks`
- [ ] File checksums match Drive's `md5Checksum`
- [ ] Local file timestamps match Drive's `modifiedTime`
- [ ] `.partial` files are cleaned up (renamed on success, deleted on failure)
- [ ] Manifest JSON is written and tracks all file statuses
- [ ] Rich progress bar shows overall and per-file progress
- [ ] Shortcuts are resolved (not downloaded as-is)
- [ ] Non-downloadable types (Forms, Sites) are skipped with log message
- [ ] Name collisions are handled with `__<id>` suffix
- [ ] `pytest tests/test_walker.py tests/test_downloader.py tests/test_checksums.py tests/test_timestamps.py tests/test_manifest.py` — all pass
- [ ] `ruff check` and `mypy` — clean
