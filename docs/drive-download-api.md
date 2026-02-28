# Research: Programmatic Google Drive Directory Download

## Table of Contents
1. [Authentication & Setup](#1-authentication--setup)
2. [Recursive Directory Traversal & Hierarchy Preservation](#2-recursive-directory-traversal--hierarchy-preservation)
3. [Downloading Files (Blob vs Google Workspace)](#3-downloading-files-blob-vs-google-workspace)
4. [Downloading Shared Files & Shared Drives](#4-downloading-shared-files--shared-drives)
5. [Preserving Created & Modified Dates](#5-preserving-created--modified-dates)
6. [Dry-Run Mode: Metadata & Size Estimation](#6-dry-run-mode-metadata--size-estimation)
7. [Rate Limits & Quotas](#7-rate-limits--quotas)
8. [Key API Fields Reference](#8-key-api-fields-reference)
9. [Recommended Architecture](#9-recommended-architecture)

---

## 1. Authentication & Setup

### Python Dependencies

```bash
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### OAuth 2.0 Flow (User Credentials)

Google Drive API requires OAuth 2.0 for accessing user data. For a download tool, you need read access scopes.

**Recommended scopes** (in order of preference):

| Scope | Type | Use Case |
|-------|------|----------|
| `https://www.googleapis.com/auth/drive.readonly` | Restricted | Read all files (My Drive + shared). Best for full backup/download. |
| `https://www.googleapis.com/auth/drive.metadata.readonly` | Restricted | Read-only metadata — good for dry-run only. |
| `https://www.googleapis.com/auth/drive.file` | Non-sensitive | Per-file access only — insufficient for downloading arbitrary directories. |
| `https://www.googleapis.com/auth/drive` | Restricted | Full read/write — overkill for download-only use. |

**For downloading an entire directory tree, `drive.readonly` is the correct scope.** It grants read access to all files in the user's Drive without write permissions.

### Authentication Code Pattern

```python
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)
```

### Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project → Enable the **Google Drive API**
3. Navigate to **APIs & Services → Credentials**
4. Create an **OAuth 2.0 Client ID** (type: Desktop application)
5. Download the JSON → rename to `credentials.json`
6. Configure the **OAuth Consent Screen** (add `drive.readonly` scope)

### Service Account (for domain-wide/server use)

Service accounts are useful for automated server-to-server downloads. Files owned by the service account live in its own isolated Drive. To access user files, use **Domain-Wide Delegation** to impersonate specific users.

---

## 2. Recursive Directory Traversal & Hierarchy Preservation

### Core Concept

Google Drive does not have a "download directory" API endpoint. You must:
1. **List** all files/folders in the target folder
2. **Recurse** into subfolders
3. **Recreate** the local directory structure
4. **Download** each file individually

### Listing Children of a Folder

```python
def list_folder_contents(service, folder_id, page_size=1000):
    """List all files and folders inside a given folder."""
    items = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            spaces='drive',
            fields='nextPageToken, files(id, name, mimeType, size, '
                   'createdTime, modifiedTime, parents, md5Checksum, '
                   'quotaBytesUsed, shared, ownedByMe, '
                   'shortcutDetails, exportLinks)',
            pageSize=page_size,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        items.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return items
```

**Key parameters:**
- `q=f"'{folder_id}' in parents and trashed=false"` — filters to children of the target folder, excludes trashed items
- `pageSize=1000` — maximum allowed per request (default is 100)
- `supportsAllDrives=True` — required to access Shared Drive files
- `includeItemsFromAllDrives=True` — includes Shared Drive items in results
- `nextPageToken` — handles pagination for folders with 1000+ items

### Recursive Traversal

```python
FOLDER_MIME = 'application/vnd.google-apps.folder'

def walk_drive(service, folder_id, local_path):
    """Recursively walk a Google Drive folder, building a file tree."""
    file_tree = []

    items = list_folder_contents(service, folder_id)

    for item in items:
        entry = {
            'id': item['id'],
            'name': item['name'],
            'mimeType': item['mimeType'],
            'localPath': os.path.join(local_path, item['name']),
            'size': int(item.get('size', 0)),
            'quotaBytesUsed': int(item.get('quotaBytesUsed', 0)),
            'createdTime': item.get('createdTime'),
            'modifiedTime': item.get('modifiedTime'),
            'md5Checksum': item.get('md5Checksum'),
            'shared': item.get('shared', False),
            'ownedByMe': item.get('ownedByMe', True),
            'isFolder': item['mimeType'] == FOLDER_MIME,
            'children': []
        }

        if item['mimeType'] == FOLDER_MIME:
            entry['children'] = walk_drive(
                service, item['id'],
                os.path.join(local_path, item['name'])
            )
        file_tree.append(entry)

    return file_tree
```

### Performance Optimization: Flat-list Approach

For very large directories (1000+ files/folders), the recursive per-folder approach can be slow due to one HTTP request per folder. An alternative **flat-list** approach fetches all files at once and reconstructs the hierarchy locally:

```python
def flat_list_all_files(service, fields=None):
    """Fetch ALL files from Drive in one pass, then reconstruct tree locally."""
    if fields is None:
        fields = ('nextPageToken, files(id, name, mimeType, size, '
                  'parents, createdTime, modifiedTime, md5Checksum, '
                  'quotaBytesUsed, shared, ownedByMe)')
    all_files = []
    page_token = None
    while True:
        response = service.files().list(
            q="trashed=false",
            spaces='drive',
            fields=fields,
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        all_files.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return all_files

def build_tree_from_flat(all_files, root_folder_id):
    """Build a tree structure from a flat file list using parent references."""
    by_id = {f['id']: f for f in all_files}
    children_map = {}
    for f in all_files:
        for pid in f.get('parents', []):
            children_map.setdefault(pid, []).append(f)

    def build(folder_id, path=''):
        result = []
        for child in children_map.get(folder_id, []):
            child_path = os.path.join(path, child['name'])
            node = {**child, 'localPath': child_path, 'subtree': []}
            if child['mimeType'] == FOLDER_MIME:
                node['subtree'] = build(child['id'], child_path)
            result.append(node)
        return result

    return build(root_folder_id)
```

**Benchmark** (from community testing): DFS recursive traversal of 1,754 files + 1,028 folders took ~409 seconds. BFS with batch processing took only ~64 seconds. The flat-list approach is often fastest for full-Drive downloads.

### Hierarchy Preservation

The local directory structure mirrors Google Drive:
- Each Drive folder → local OS directory (`os.makedirs(path, exist_ok=True)`)
- Each Drive file → local file at the corresponding path
- Folder `parents` field maps a file to its parent (single parent per file since September 2020)

---

## 3. Downloading Files (Blob vs Google Workspace)

Google Drive has two fundamentally different file categories that require different download methods.

### Blob Files (Regular Files)

Binary/text files (PDFs, images, videos, ZIPs, etc.) are downloaded directly using `files.get` with `alt=media`:

```python
import io
from googleapiclient.http import MediaIoBaseDownload

def download_blob_file(service, file_id, destination_path):
    """Download a regular (blob) file from Drive."""
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(destination_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.close()
```

### Google Workspace Documents (Docs, Sheets, Slides)

Google Workspace documents have no "file content" — they must be **exported** to a standard format. The `files.export` method is used, and exported content is limited to 10 MB.

**Default export format mapping:**

| Google Workspace Type | MIME Type | Recommended Export | Extension |
|----------------------|-----------|-------------------|-----------|
| Google Docs | `application/vnd.google-apps.document` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `.docx` |
| Google Sheets | `application/vnd.google-apps.spreadsheet` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `.xlsx` |
| Google Slides | `application/vnd.google-apps.presentation` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `.pptx` |
| Google Drawings | `application/vnd.google-apps.drawing` | `application/pdf` | `.pdf` |
| Google Apps Script | `application/vnd.google-apps.script` | `application/vnd.google-apps.script+json` | `.json` |
| Google Vids | `application/vnd.google-apps.vid` | `video/mp4` (via `files.download` long-running op) | `.mp4` |
| Google Forms | `application/vnd.google-apps.form` | *(cannot be exported)* | — |
| Google Sites | `application/vnd.google-apps.site` | *(cannot be exported)* | — |

> **Additional export formats available** (not shown as defaults above):
> - Google Docs also supports: PDF, plain text (`text/plain`), Rich Text (`application/rtf`), EPUB (`application/epub+zip`), Markdown (`text/markdown` → `.md`), HTML, and Open Document (`application/vnd.oasis.opendocument.text`)
> - Google Sheets also supports: PDF, CSV (first sheet only), TSV, HTML, and Open Document Spreadsheet
> - Google Slides also supports: PDF and Open Document Presentation
> - Google Drawings also supports: JPEG, PNG, SVG
>
> Use `about.get` with `fields=exportFormats` to retrieve the full list of supported export formats at runtime.

Alternative export options include PDF (`application/pdf`) for any document, plain text, CSV (for Sheets), SVG/PNG (for Drawings), etc.

```python
EXPORT_MIME_MAP = {
    'application/vnd.google-apps.document':
        ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
    'application/vnd.google-apps.spreadsheet':
        ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx'),
    'application/vnd.google-apps.presentation':
        ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx'),
    'application/vnd.google-apps.drawing':
        ('application/pdf', '.pdf'),
    'application/vnd.google-apps.script':
        ('application/vnd.google-apps.script+json', '.json'),
    # Google Vids require files.download (long-running operation), not files.export
    # 'application/vnd.google-apps.vid': ('video/mp4', '.mp4'),
}

# Types that cannot be downloaded or exported
NON_DOWNLOADABLE = {
    'application/vnd.google-apps.form',
    'application/vnd.google-apps.site',
    'application/vnd.google-apps.map',
    'application/vnd.google-apps.fusiontable',
    'application/vnd.google-apps.folder',
    'application/vnd.google-apps.shortcut',
    'application/vnd.google-apps.drive-sdk',
}

def download_file(service, file_metadata, destination_path):
    """Download a file, handling both blob and Workspace types."""
    mime = file_metadata['mimeType']

    if mime in NON_DOWNLOADABLE:
        return None  # Skip non-downloadable types

    if mime.startswith('application/vnd.google-apps.'):
        # Google Workspace file — must export
        if mime not in EXPORT_MIME_MAP:
            return None  # Unknown Workspace type
        export_mime, ext = EXPORT_MIME_MAP[mime]
        destination_path += ext  # Append appropriate extension
        request = service.files().export_media(
            fileId=file_metadata['id'], mimeType=export_mime)
    else:
        # Regular blob file — direct download
        request = service.files().get_media(fileId=file_metadata['id'])

    fh = io.FileIO(destination_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.close()
    return destination_path
```

### Files That Cannot Be Downloaded
- **Folders** — containers only, no content to download
- **Shortcuts** — metadata-only pointers; resolve via `shortcutDetails.targetId`
- **Third-party shortcuts** — links to external storage; no content in Drive
- **Google Forms, Sites, Maps, Fusion Tables** — no export available

### Handling Shortcuts

Shortcuts (`application/vnd.google-apps.shortcut`) point to another file. Include `shortcutDetails` in your fields request to get the target:

```python
# When listing files, include shortcutDetails in fields
# shortcutDetails contains: targetId, targetMimeType, targetResourceKey
if item['mimeType'] == 'application/vnd.google-apps.shortcut':
    target_id = item['shortcutDetails']['targetId']
    target_mime = item['shortcutDetails']['targetMimeType']
    # Download the target file instead
```

---

## 4. Downloading Shared Files & Shared Drives

### "Shared with Me" Files

Files shared with you (but not in your My Drive) can be queried with:

```python
# List files shared with me
response = service.files().list(
    q="sharedWithMe=true and trashed=false",
    fields='nextPageToken, files(id, name, mimeType, size, '
           'createdTime, modifiedTime, parents, shared, owners, '
           'sharingUser, sharedWithMeTime)',
    pageSize=1000
).execute()
```

**Key query operators for shared files:**
- `sharedWithMe=true` — files explicitly shared with the authenticated user
- `'me' in owners` — files owned by the authenticated user
- `not 'me' in owners` — files owned by others (shared files)

### Shared Drives (formerly Team Drives)

Shared Drives are organizational drives where files are owned by the group, not individuals. Accessing them requires two critical parameters on every API call:

```python
# List contents of a Shared Drive folder
response = service.files().list(
    q=f"'{shared_drive_folder_id}' in parents and trashed=false",
    corpora='drive',
    driveId='SHARED_DRIVE_ID',
    supportsAllDrives=True,
    includeItemsFromAllDrives=True,
    fields='nextPageToken, files(id, name, mimeType, size, '
           'createdTime, modifiedTime, parents, driveId)',
    pageSize=1000
).execute()
```

**Critical parameters for Shared Drives:**

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `supportsAllDrives` | `True` | Declares your app supports Shared Drives |
| `includeItemsFromAllDrives` | `True` | Includes Shared Drive items in results |
| `corpora` | `'drive'` | Search within a specific Shared Drive |
| `driveId` | `'<shared_drive_id>'` | ID of the target Shared Drive |

Without `supportsAllDrives=True`, you'll get a **404: File Not Found** error when accessing Shared Drive files, even with the correct file ID.

### Listing All Shared Drives

```python
def list_shared_drives(service):
    """List all Shared Drives the user has access to."""
    drives = []
    page_token = None
    while True:
        response = service.drives().list(
            pageSize=100,
            pageToken=page_token,
            fields='nextPageToken, drives(id, name)'
        ).execute()
        drives.extend(response.get('drives', []))
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return drives
```

### Downloading from Shared Drives

The `files.get_media()` call for downloading also requires `supportsAllDrives=True`:

```python
request = service.files().get_media(
    fileId=file_id,
    supportsAllDrives=True
)
```

### Download Restrictions

Some files may have download restrictions set by their owner. Check the `capabilities.canDownload` field before attempting:

```python
file_meta = service.files().get(
    fileId=file_id,
    fields='capabilities/canDownload',
    supportsAllDrives=True
).execute()
if not file_meta['capabilities']['canDownload']:
    print(f"Download restricted for file {file_id}")
```

---

## 5. Preserving Created & Modified Dates

### Retrieving Timestamps from the API

The Google Drive API provides these timestamp fields (all RFC 3339 / ISO 8601 format):

| Field | Description |
|-------|-------------|
| `createdTime` | When the file was originally created |
| `modifiedTime` | When the file was last modified by anyone |
| `modifiedByMeTime` | When the file was last modified by the authenticated user |
| `viewedByMeTime` | When the file was last viewed by the authenticated user |
| `sharedWithMeTime` | When the file was shared with the authenticated user |

Request these fields explicitly:

```python
fields = 'files(id, name, mimeType, size, createdTime, modifiedTime)'
```

### Applying Timestamps to Local Files

After downloading, use `os.utime()` to set local file modification and access times:

```python
import os
from datetime import datetime, timezone

def parse_drive_time(time_str):
    """Parse Google Drive RFC 3339 timestamp to Unix timestamp."""
    if not time_str:
        return None
    # Drive timestamps: "2024-01-15T10:30:00.000Z"
    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    return dt.timestamp()

def preserve_timestamps(local_path, created_time_str, modified_time_str):
    """Set the local file's atime and mtime to match Google Drive metadata."""
    mtime = parse_drive_time(modified_time_str)
    atime = parse_drive_time(created_time_str) or mtime  # Use created as atime

    if mtime:
        os.utime(local_path, (atime, mtime))
```

### Platform Considerations

| OS | `mtime` (modified) | `atime` (access) | `ctime`/birthtime (created) |
|----|----|----|-----|
| **Linux** | `os.utime()` ✅ | `os.utime()` ✅ | Cannot be set programmatically (filesystem-level) |
| **macOS** | `os.utime()` ✅ | `os.utime()` ✅ | Can be set via `SetFile -d` or `xattr`, but not via standard Python |
| **Windows** | `os.utime()` ✅ | `os.utime()` ✅ | Can set via `win32file.SetFileTime()` (pywin32), but unreliable in practice |

**Recommendation:** Always set `mtime` (reliable on all platforms). Map `createdTime` → `atime` as a best-effort preservation. Store the full original metadata in a sidecar JSON/YAML file for complete fidelity.

### Google Drive Timestamp Precision

Google Drive stores timestamps with **millisecond** resolution. Typical Unix/Windows filesystems also support sub-second resolution, so the mapping is generally exact.

---

## 6. Dry-Run Mode: Metadata & Size Estimation

A dry-run traverses the directory tree and collects metadata without downloading any file content. This lets you report expected download size, file counts, and structural information.

### Size Fields

| Field | Description | Available For |
|-------|-------------|---------------|
| `size` | File content size in bytes | Blob files only |
| `quotaBytesUsed` | Storage quota consumed (includes revisions) | All files |

**Important:** Google Workspace documents (Docs, Sheets, Slides) have `size=0` because they have no stored binary content. They only have size after export, and the exported size isn't known until the export is performed. You can estimate exported sizes but cannot know them exactly without performing the export.

### Dry-Run Implementation

```python
def dry_run(service, folder_id, path='', depth=0):
    """Walk the directory tree and collect metadata without downloading."""
    stats = {
        'total_files': 0,
        'total_folders': 0,
        'total_size_bytes': 0,
        'total_quota_bytes': 0,
        'google_workspace_files': 0,
        'non_downloadable_files': 0,
        'files': []
    }

    items = list_folder_contents(service, folder_id)

    for item in items:
        name = item['name']
        mime = item['mimeType']
        file_size = int(item.get('size', 0))
        quota_used = int(item.get('quotaBytesUsed', 0))
        local_path = os.path.join(path, name)

        entry = {
            'id': item['id'],
            'name': name,
            'localPath': local_path,
            'mimeType': mime,
            'size': file_size,
            'quotaBytesUsed': quota_used,
            'createdTime': item.get('createdTime'),
            'modifiedTime': item.get('modifiedTime'),
            'md5Checksum': item.get('md5Checksum'),
            'shared': item.get('shared', False),
            'ownedByMe': item.get('ownedByMe', True),
        }

        if mime == FOLDER_MIME:
            stats['total_folders'] += 1
            sub_stats = dry_run(service, item['id'], local_path, depth + 1)
            stats['total_files'] += sub_stats['total_files']
            stats['total_folders'] += sub_stats['total_folders']
            stats['total_size_bytes'] += sub_stats['total_size_bytes']
            stats['total_quota_bytes'] += sub_stats['total_quota_bytes']
            stats['google_workspace_files'] += sub_stats['google_workspace_files']
            stats['non_downloadable_files'] += sub_stats['non_downloadable_files']
            stats['files'].extend(sub_stats['files'])
        elif mime in NON_DOWNLOADABLE:
            stats['non_downloadable_files'] += 1
        elif mime.startswith('application/vnd.google-apps.'):
            stats['google_workspace_files'] += 1
            stats['total_quota_bytes'] += quota_used
            entry['note'] = 'Will be exported (size unknown until export)'
            stats['files'].append(entry)
        else:
            stats['total_files'] += 1
            stats['total_size_bytes'] += file_size
            stats['total_quota_bytes'] += quota_used
            stats['files'].append(entry)

    return stats

def print_dry_run_report(stats):
    """Print a human-readable dry-run summary."""
    def fmt_size(b):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if b < 1024:
                return f"{b:.2f} {unit}"
            b /= 1024

    print("=" * 60)
    print("DRY RUN REPORT")
    print("=" * 60)
    print(f"Total downloadable files:    {stats['total_files']}")
    print(f"Total folders:               {stats['total_folders']}")
    print(f"Google Workspace files:      {stats['google_workspace_files']}")
    print(f"  (exported size unknown until download)")
    print(f"Non-downloadable items:      {stats['non_downloadable_files']}")
    print(f"  (Forms, Sites, shortcuts, etc.)")
    print(f"Estimated download size:     {fmt_size(stats['total_size_bytes'])}")
    print(f"  (blob files only — excludes Workspace exports)")
    print(f"Total Drive quota used:      {fmt_size(stats['total_quota_bytes'])}")
    print("=" * 60)
```

### Metadata Sidecar File

For full fidelity, save a JSON manifest alongside the download:

```python
import json

def save_manifest(stats, output_path):
    """Save the full file tree metadata as a JSON manifest."""
    manifest = {
        'driveRootId': '<folder_id>',
        'downloadDate': datetime.now(timezone.utc).isoformat(),
        'summary': {
            'totalFiles': stats['total_files'],
            'totalFolders': stats['total_folders'],
            'totalSizeBytes': stats['total_size_bytes'],
            'googleWorkspaceFiles': stats['google_workspace_files'],
            'nonDownloadableFiles': stats['non_downloadable_files'],
        },
        'files': stats['files']
    }
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)
```

---

## 7. Rate Limits & Quotas

### Default API Quotas

| Limit | Value | Notes |
|-------|-------|-------|
| Queries per 60 seconds (project) | 12,000 | Sum of read + write (~200 req/sec) |
| Queries per 60 seconds (user) | 12,000 | Can be adjusted in Cloud Console (up to project limit) |
| Daily query limit | Unlimited | As long as per-minute limits are respected |
| Sustained write rate | ~3 req/sec | Unofficial soft limit |
| File export limit | 10 MB | Per `files.export` call |
| Download bandwidth | ~10 GB/day (approximate) | Undocumented; varies by account type |

> **Note:** Older documentation cited 20,000 queries per 100 seconds (project) and 2,400 per 100 seconds (user). These figures are outdated. Always check the [current Usage Limits page](https://developers.google.com/workspace/drive/api/guides/limits) for the latest quotas. A higher project quota can be requested in the Google Cloud Console.

### Error Codes

| Code | Reason | Action |
|------|--------|--------|
| `403` | `userRateLimitExceeded` or `rateLimitExceeded` | Exponential backoff; reduce per-user request rate |
| `429` | Too Many Requests (backend rate limit) | Exponential backoff; reduce overall request rate |
| `403` | `downloadQuotaExceeded` | Undocumented daily limit; wait ~24 hours or spread across accounts |
| `404` | `notFound` | Check `supportsAllDrives=True` for Shared Drive files; verify file ID and permissions |
| `403` | `domainPolicy` | Domain admin has disabled Drive apps; contact admin |

> **Note:** Both 403 and 429 can indicate rate limiting. The `googleapiclient` library raises `HttpError` with `resp.status` as an integer. Always check the error `reason` field in the response body for the specific cause.

### Exponential Backoff Pattern

```python
import time
import random
from googleapiclient.errors import HttpError

def api_call_with_backoff(callable_fn, max_retries=5):
    """Execute an API call with exponential backoff on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return callable_fn()
        except HttpError as e:
            if e.resp.status in (403, 429) and attempt < max_retries - 1:
                wait = (2 ** attempt) + random.random()
                print(f"Rate limited ({e.resp.status}). "
                      f"Retrying in {wait:.1f}s (attempt {attempt + 1})")
                time.sleep(wait)
            else:
                raise
```

---

## 8. Key API Fields Reference

### files.list / files.get Fields

These are the most important fields for a download tool. Request them explicitly using the `fields` parameter:

```
files(
    id,
    name,
    mimeType,
    size,
    quotaBytesUsed,
    createdTime,
    modifiedTime,
    modifiedByMeTime,
    parents,
    md5Checksum,
    sha1Checksum,
    sha256Checksum,
    shared,
    ownedByMe,
    owners,
    capabilities/canDownload,
    shortcutDetails/targetId,
    shortcutDetails/targetMimeType,
    webContentLink,
    exportLinks,
    trashed,
    driveId
)
```

### Search Query Operators

| Operator | Example | Description |
|----------|---------|-------------|
| `in parents` | `'FOLDER_ID' in parents` | Children of a folder |
| `trashed` | `trashed=false` | Exclude trashed files |
| `mimeType` | `mimeType='application/pdf'` | Filter by type |
| `sharedWithMe` | `sharedWithMe=true` | Files shared with me |
| `owners` | `'me' in owners` | Files I own |
| `modifiedTime` | `modifiedTime > '2024-01-01'` | Recently modified |
| `name contains` | `name contains 'report'` | Name search |

---

## 9. Recommended Architecture

### High-Level Flow

```
1. Authenticate (OAuth2 / Service Account)
2. Resolve root folder ID (from URL, ID, or 'root' for My Drive)
3. Phase 1: WALK — Recursively traverse and collect metadata
4. Phase 2: DRY RUN REPORT — Display stats, prompt user
5. Phase 3: DOWNLOAD — Download files with:
   a. Create local directories
   b. Download blob files (files.get_media)
   c. Export Workspace files (files.export_media)
   d. Resolve & follow shortcuts
   e. Apply timestamps (os.utime)
   f. Verify checksums (md5Checksum)
6. Save manifest JSON
```

### Folder ID Extraction

```python
import re

def extract_folder_id(url_or_id):
    """Extract a Google Drive folder ID from a URL or return as-is."""
    # Direct ID
    if re.match(r'^[a-zA-Z0-9_-]+$', url_or_id):
        return url_or_id
    # URL patterns
    patterns = [
        r'/folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    raise ValueError(f"Cannot extract folder ID from: {url_or_id}")
```

### Checksum Verification

```python
import hashlib

def verify_md5(local_path, expected_md5):
    """Verify a downloaded file's MD5 matches the Drive metadata."""
    if not expected_md5:
        return None  # No checksum available (Workspace files don't have one)
    md5 = hashlib.md5()
    with open(local_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            md5.update(chunk)
    actual = md5.hexdigest()
    return actual == expected_md5
```

### Key Design Decisions

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Traversal strategy | Flat-list for full Drive; recursive for single folders | Flat-list reduces HTTP calls dramatically for large drives |
| Workspace export format | Office XML (docx/xlsx/pptx) | Preserves formatting; widely compatible |
| Timestamp preservation | `os.utime()` for mtime; sidecar JSON for createdTime | Cross-platform reliable for mtime; createdTime not settable on Linux |
| Shared Drive support | Always pass `supportsAllDrives=True` | Prevents 404 errors on any Shared Drive content |
| Rate limiting | Exponential backoff with jitter | Required by Google's guidelines |
| Checksum | Verify `md5Checksum` post-download | Only available for blob files; Workspace exports have no checksum |

---

## References

- [Google Drive API Overview](https://developers.google.com/workspace/drive/api/guides/about-sdk)
- [Files Resource (v3)](https://developers.google.com/workspace/drive/api/reference/rest/v3/files)
- [Download & Export Files](https://developers.google.com/workspace/drive/api/guides/manage-downloads)
- [Choose API Scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [File Metadata Guide](https://developers.google.com/workspace/drive/api/guides/file-metadata)
- [Export MIME Types](https://developers.google.com/workspace/drive/api/guides/ref-export-formats)
- [Search Query Reference](https://developers.google.com/workspace/drive/api/guides/ref-search-terms)
- [Usage Limits](https://developers.google.com/workspace/drive/api/guides/limits)
- [Shared Drives Guide](https://developers.google.com/workspace/drive/api/guides/about-shareddrives)
- [Resolve Errors](https://developers.google.com/workspace/drive/api/guides/handle-errors)
- [Python Quickstart](https://developers.google.com/workspace/drive/api/quickstart/python)
- [google-api-python-client](https://github.com/googleapis/google-api-python-client)
