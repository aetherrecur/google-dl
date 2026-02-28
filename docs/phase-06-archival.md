# Phase 6: Archival Features

**Status:** `pending`
**Estimated effort:** Day 11–14
**Depends on:** Phase 2 (walker + download)
**Blocks:** Nothing

---

## Objective

Implement the four archival features: permissions snapshot, comments preservation, metadata sidecar, and revision history download. Each is independent and can be developed in parallel.

**Implementation order:** permissions → comments → metadata → revisions (simplest to most complex).

---

## Deliverables

### 1. `archival.py` — Permissions Snapshot (`--permissions`)

**Reference:** [development-plan.md §9](development-plan.md#9-archival-features)

#### API Call

```python
def save_permissions(service, item: DriveItem, output_dir: Path, throttler):
    """Fetch and save permissions for a file/folder."""
    perms = throttled_execute(
        service.permissions().list(
            fileId=item.id,
            supportsAllDrives=True,
            fields="permissions(id,type,role,emailAddress,displayName,domain,"
                   "expirationTime,allowFileDiscovery,deleted,pendingOwner,"
                   "permissionDetails(permissionType,role,inherited,inheritedFrom))"
        ),
        throttler
    )
```

#### Sidecar Format

- Files: `Q3 Report.docx.permissions.json`
- Folders: `reports/.folder.permissions.json`

```json
{
  "fileId": "1ABC123xyz",
  "fileName": "Q3 Report.docx",
  "capturedAt": "2026-02-28T20:00:00Z",
  "permissions": [...],
  "summary": {
    "directPermissions": 3,
    "inheritedPermissions": 2
  }
}
```

#### Optimization
- Concurrent fetching with 4-thread pool
- Skip re-fetch on `--resume` if `modifiedTime` unchanged

### 2. `archival.py` — Comments Preservation (`--comments`)

**Reference:** [development-plan.md §9](development-plan.md#9-archival-features)

#### API Call

```python
def save_comments(service, item: DriveItem, output_dir: Path, throttler):
    """Fetch and save comments for a file."""
    comments = throttled_execute(
        service.comments().list(
            fileId=item.id,
            fields="comments(id,author(displayName,emailAddress),content,"
                   "createdTime,modifiedTime,resolved,anchor,replies("
                   "author(displayName,emailAddress),content,createdTime,modifiedTime))",
            includeDeleted=False,
        ),
        throttler
    )
```

#### Optimization
- Check `commentCount` from walker metadata — if 0, skip API call entirely
- `fields` parameter is **mandatory** (API returns nothing without it)

#### Sidecar Format

`Q3 Report.docx.comments.json`:

```json
{
  "fileId": "1ABC123xyz",
  "fileName": "Q3 Report.docx",
  "capturedAt": "...",
  "commentCount": 5,
  "comments": [
    {
      "id": "comment123",
      "author": { "displayName": "...", "emailAddress": "..." },
      "content": "...",
      "createdTime": "...",
      "resolved": true,
      "anchor": "raw opaque string",
      "replies": [...]
    }
  ]
}
```

#### Anchored Comments
- `anchor` field is opaque JSON — store raw string verbatim
- Best-effort parse into `anchorParsed` field
- Positions reference internal revision IDs — cannot map to exported file positions

### 3. `archival.py` — Metadata Sidecar (`--metadata`)

```python
def save_metadata(item: DriveItem, output_dir: Path):
    """Serialize DriveItem fields to metadata sidecar."""
```

- Pure local operation — no API calls
- Sidecar: `Q3 Report.docx.metadata.json`
- Includes: id, name, mimeType, size, md5Checksum, createdTime, modifiedTime, parents, drive_path, sharing status, owner

### 4. `archival.py` — Revision History (`--revisions [N]`)

**Reference:** [development-plan.md §9](development-plan.md#9-archival-features)

#### API Call

```python
def save_revisions(service, item: DriveItem, output_dir: Path,
                   revision_count: Optional[int], throttler, creds):
    """List and download revision history for a file."""
    revisions = throttled_execute(
        service.revisions().list(
            fileId=item.id,
            fields="revisions(id,modifiedTime,mimeType,keepForever,"
                   "originalFilename,size,exportLinks)"
        ),
        throttler
    )
```

#### Critical Constraint: `drive.readonly` Scope

| Type | `revisions.list` | Blob download | Export via `exportLinks` |
|------|-------------------|---------------|------------------------|
| Blob files | Yes | Only if `keepForever` | N/A |
| Google Docs | Yes (may be incomplete) | No | Yes |
| Google Sheets | Yes (may be incomplete) | No | Yes |
| Google Slides | Yes (may be incomplete) | No | Yes |

#### Revision Selection

- `--revisions` (no value) → all revisions (`revision_count=0`)
- `--revisions N` → last N revisions: `revisions[-N:]`
- Sort chronologically by `modifiedTime`

#### Naming Convention

```
backup/reports/
  Q3 Report.docx                                    # current version
  Q3 Report.docx.revisions/
    2026-01-15T10:30:00Z_rev123_Q3 Report.docx      # revision 1
    2026-02-01T14:20:00Z_rev456_Q3 Report.docx      # revision 2
    revisions.json                                    # revision metadata
```

Safe timestamp format: replace `:` with `-` in filenames.

#### Download Strategy

- Blob revisions: `service.revisions().get_media(fileId=..., revisionId=...)` — only if `keepForever=True`
- Workspace revisions: use per-revision `exportLinks` with Bearer token auth
- Both: write to `.partial` first, atomic rename on completion

### 5. Error Handling

All archival operations are **best-effort**:

```python
try:
    save_permissions(service, item, output_dir, throttler)
except GdriveError as e:
    logger.warning(f"Failed to save permissions for {item.name}: {e}")
    # Continue with download — archival failure is non-fatal
```

### 6. CLI Options

```python
@click.option("--permissions", is_flag=True, help="Save permissions manifest per file")
@click.option("--comments", is_flag=True, help="Export comments as sidecar files")
@click.option("--revisions", type=int, is_flag=False, flag_value=0, default=None,
              help="Download revision history. No value=all, N=N most recent")
@click.option("--metadata", is_flag=True, help="Save Drive metadata as sidecar JSON")
```

---

## Tests (Write First)

### `test_archival.py`

```python
# Permissions
def test_save_permissions_creates_sidecar():
    """Permissions sidecar is created alongside the file."""

def test_permissions_sidecar_format():
    """Sidecar contains fileId, fileName, capturedAt, permissions list, summary."""

def test_permissions_folder_sidecar_naming():
    """Folder permissions saved as .folder.permissions.json."""

def test_permissions_inherited_vs_direct():
    """Summary correctly counts inherited and direct permissions."""

def test_permissions_skip_on_resume_unchanged():
    """Skip permissions fetch if modifiedTime unchanged on resume."""

# Comments
def test_save_comments_creates_sidecar():
    """Comments sidecar is created for files with comments."""

def test_save_comments_skips_zero_count():
    """Files with commentCount=0 skip the API call."""

def test_comments_include_replies():
    """Comment replies are nested in the sidecar."""

def test_comments_anchor_preserved_raw():
    """Anchor field stored as raw string."""

# Metadata
def test_save_metadata_no_api_call():
    """Metadata sidecar uses only local DriveItem data."""

def test_metadata_sidecar_format():
    """Metadata contains all DriveItem fields."""

# Revisions
def test_save_revisions_all():
    """--revisions (no value) downloads all revisions."""

def test_save_revisions_last_n():
    """--revisions 3 downloads only last 3 revisions."""

def test_revisions_blob_requires_keep_forever():
    """Blob revision download only attempted if keepForever=True."""

def test_revisions_workspace_uses_export_links():
    """Workspace revisions exported via exportLinks."""

def test_revisions_naming_convention():
    """Revision files named with timestamp_revisionId_originalName."""

def test_revisions_metadata_json():
    """revisions.json metadata file created in .revisions/ directory."""

# Error handling
def test_archival_failure_non_fatal():
    """Archival API error is caught and logged, download continues."""
```

---

## Verification Checklist

- [ ] `--permissions` creates `.permissions.json` for each file and folder
- [ ] `--comments` creates `.comments.json` for files with comments
- [ ] `--metadata` creates `.metadata.json` with full Drive metadata
- [ ] `--revisions` downloads revision files into `.revisions/` directory
- [ ] `--revisions 3` downloads only the 3 most recent revisions
- [ ] Blob revisions only downloaded if `keepForever=True`
- [ ] Workspace revisions exported via `exportLinks`
- [ ] Archival failures don't stop the download
- [ ] Sidecar files have correct naming conventions
- [ ] `pytest tests/test_archival.py` — all pass
