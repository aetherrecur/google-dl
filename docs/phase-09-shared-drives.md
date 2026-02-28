# Phase 9: Shared Drives

**Status:** `completed`
**Estimated effort:** Day 18
**Depends on:** Phase 2 (walker + download)
**Blocks:** Nothing

---

## Objective

Implement Shared Drive support: automatic detection, `DriveContext` for API call parameterization, auto-discovery via `drives.list`, and the `--shared-drives=list` interactive selector.

---

## Deliverables

### 1. `DriveContext` Dataclass

**Reference:** [development-plan.md §6](development-plan.md#6-directory-walker)

```python
@dataclass
class DriveContext:
    drive_type: Literal["my_drive", "shared_drive"]
    drive_id: Optional[str]

    def list_kwargs(self) -> dict:
        """Return kwargs for files.list API calls."""
        kwargs = {"supportsAllDrives": True, "includeItemsFromAllDrives": True}
        if self.drive_type == "shared_drive":
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = self.drive_id
        return kwargs
```

Pass `**ctx.list_kwargs()` into every API call to centralize Shared Drive boilerplate.

### 2. Shared Drive Detection

```python
def detect_drive_context(service, folder_id: str) -> DriveContext:
    """Determine if folder is in My Drive or a Shared Drive."""
    meta = service.files().get(
        fileId=folder_id,
        fields="id,driveId",
        supportsAllDrives=True,
    ).execute()

    if meta.get("driveId"):
        return DriveContext("shared_drive", meta["driveId"])
    return DriveContext("my_drive", None)
```

### 3. Auto-Discovery via `drives.list`

```python
def list_shared_drives(service) -> list[dict]:
    """List all accessible Shared Drives."""
    drives = []
    page_token = None
    while True:
        result = service.drives().list(
            pageSize=100,
            pageToken=page_token,
            fields="nextPageToken,drives(id,name,createdTime)",
        ).execute()
        drives.extend(result.get("drives", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return drives
```

### 4. Interactive Selector (`--shared-drives=list`)

When `--shared-drives=list`:
1. Call `list_shared_drives()` to enumerate accessible drives
2. Display numbered list with drive names
3. Prompt user to select which drives to download
4. Process each selected drive as a separate download

```python
def select_shared_drives(service) -> list[dict]:
    """Interactive selection of Shared Drives."""
    drives = list_shared_drives(service)
    if not drives:
        click.echo("No Shared Drives accessible.")
        return []

    click.echo("Accessible Shared Drives:")
    for i, drive in enumerate(drives, 1):
        click.echo(f"  {i}. {drive['name']}")

    selection = click.prompt("Select drives (comma-separated numbers, or 'all')")
    # Parse selection and return matching drives
```

### 5. CLI Options

```python
@click.option("--shared-drives", default=None,
              help="Include Shared Drives. Use '=list' to select interactively.")
```

### 6. Integration with Walker

- `walker.walk()` uses `DriveContext.list_kwargs()` on every `files.list` call
- Shared Drive files that restrict downloads (`capabilities.canDownload = false`) are flagged and skipped
- `supportsAllDrives=True` is set on **all** API calls (files.get, permissions.list, etc.)

---

## Tests (Write First)

### `test_walker.py` (Shared Drive additions)

```python
def test_detect_my_drive_context():
    """Folder without driveId returns my_drive context."""

def test_detect_shared_drive_context():
    """Folder with driveId returns shared_drive context with drive ID."""

def test_drive_context_list_kwargs_my_drive():
    """my_drive context includes supportsAllDrives but no corpora/driveId."""

def test_drive_context_list_kwargs_shared_drive():
    """shared_drive context includes corpora='drive' and driveId."""

def test_list_shared_drives_pagination():
    """list_shared_drives handles multiple pages."""

def test_list_shared_drives_empty():
    """list_shared_drives returns empty list when no drives accessible."""

def test_shared_drive_can_download_false_skipped():
    """Files with canDownload=false are skipped with reason."""

def test_all_api_calls_include_supports_all_drives():
    """supportsAllDrives=True is set on all API calls."""
```

---

## Verification Checklist

- [ ] Shared Drive folders download correctly
- [ ] `DriveContext` correctly detects My Drive vs Shared Drive
- [ ] All API calls include `supportsAllDrives=True`
- [ ] Shared Drive calls include `corpora=drive` and `driveId`
- [ ] `--shared-drives=list` shows available Shared Drives
- [ ] Interactive selector works with comma-separated and 'all' input
- [ ] Non-downloadable Shared Drive files are skipped with reason
- [ ] `pytest` — all Shared Drive tests pass
