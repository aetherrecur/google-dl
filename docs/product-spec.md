# gdrive-dl

A command-line tool for downloading and archiving Google Drive directories with full context preservation. Unlike general-purpose sync tools, `gdrive-dl` captures not just files but their permissions, comments, revision history, and metadata — everything needed for compliance, offboarding, legal discovery, or deep backups.

**Core philosophy:** rclone is "rsync for cloud storage" (broad, sync-focused). `gdrive-dl` is "Google Drive archival done right" (deep, download/preservation-focused).

## Features

- **Recursive directory download** with local hierarchy preservation
- **Permissions snapshot** — captures who has access to every file and folder (roles, emails, link-sharing settings, expiration dates)
- **Revision history download** — downloads previous versions of files, not just the current one
- **Comments & metadata preservation** — exports comments, descriptions, and star status as sidecar files
- **Smart Workspace export** — configurable per-directory or per-file export formats, with dual-export support (e.g., both `.docx` and `.pdf`)
- **Rich dry-run** — estimates file count, download size, API call count, and wall-clock time before downloading anything
- **Two-tier filtering** — API-pushdown queries for speed, post-fetch filters for metadata the API can't query (with cost warnings)
- **Timestamp preservation** — restores `modifiedTime` on local files; stores `createdTime` in the download manifest
- **Integrity verification** — MD5 checksum verification for blob files with a persistent download manifest for resumable sessions
- **Shared Drive auto-discovery** — finds all accessible Shared Drives without manual drive ID configuration
- **Post-download report** — Markdown summary of what was downloaded, skipped, and any errors encountered

## Installation

### Prerequisites

- Python 3.9+
- A Google Cloud project with the Drive API enabled
- OAuth 2.0 Client ID credentials (Desktop app type)

### Setup

```bash
pip install gdrive-dl
```

Or from source:

```bash
git clone https://github.com/yourname/gdrive-dl.git
cd gdrive-dl
pip install -e .
```

### Google Cloud Configuration

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Enable the **Google Drive API** under APIs & Services → Library.
4. Go to APIs & Services → Credentials → Create Credentials → **OAuth 2.0 Client ID**.
5. Select application type: **Desktop app**.
6. Download the JSON file and save it as `credentials.json` in your working directory.
7. Configure the **OAuth consent screen** with your app name and support email. For personal use, "External" user type in testing mode is sufficient (limited to 100 test users, no verification required).

## Quick Start

```bash
# Download a folder by URL
gdrive-dl https://drive.google.com/drive/folders/1ABC123xyz

# Download by folder ID
gdrive-dl 1ABC123xyz

# Download your entire My Drive
gdrive-dl root

# Dry run first to see what would happen
gdrive-dl --dry-run https://drive.google.com/drive/folders/1ABC123xyz

# Download with full archival context
gdrive-dl --permissions --comments --revisions ./backup https://drive.google.com/drive/folders/1ABC123xyz
```

On first run, a browser window opens for Google OAuth sign-in. Credentials are cached in `token.json` for subsequent runs.

## Usage

```
gdrive-dl [OPTIONS] [OUTPUT_DIR] SOURCE
```

`SOURCE` is a Google Drive folder URL, folder ID, or `root` for My Drive.
`OUTPUT_DIR` defaults to `./<folder_name>/` if not specified.

### Core Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Show what would be downloaded without downloading. Displays file count, estimated size, API call count, predicted time, and non-downloadable items. |
| `-o, --output DIR` | Output directory (default: `./<folder_name>/`). |
| `--flat` | Don't preserve directory hierarchy; download all files into a single directory. |
| `--shared-drives` | Include Shared Drives. Use `--shared-drives=list` to interactively select which drives to include. |
| `--config FILE` | Load options from a YAML config file. CLI flags override config values. |

### Authentication

| Flag | Description |
|------|-------------|
| `--credentials FILE` | Path to OAuth credentials JSON (default: `./credentials.json`). |
| `--token FILE` | Path to cached token file (default: `./token.json`). |
| `--service-account FILE` | Use a service account key file instead of OAuth. |
| `--browser BROWSER` | Browser to open for OAuth sign-in (e.g., `chrome`, `firefox`). Default: system default. See [Browser Selection](#browser-selection). |
| `--no-browser` | Don't open a browser; print the authorization URL to the console instead. For headless/SSH/Docker environments. |

### Archival Options

| Flag | Description |
|------|-------------|
| `--permissions` | Save a permissions manifest for each file and folder (JSON sidecar). |
| `--comments` | Export file comments as sidecar files (JSON). |
| `--revisions [N]` | Download revision history. `--revisions` downloads all available; `--revisions 5` downloads the 5 most recent. See [Revision History Caveats](#revision-history). |
| `--metadata` | Save full Drive metadata (description, star status, sharing details) as sidecar JSON per file. |

### Filtering

`gdrive-dl` provides two filtering tiers with different performance characteristics:

| Flag | Description |
|------|-------------|
| `--query QUERY` | **API-level filter.** Passed directly to the Drive API `files.list` `q` parameter. Fast — reduces data fetched from the API. |
| `--filter EXPRESSION` | **Post-fetch filter.** Applied locally after metadata is retrieved. Supports predicates the API can't query natively (e.g., specific sharing users). Requires additional API calls per file. |
| `--filter-confirm` | Required when `--filter` would trigger expensive operations (>100 additional API calls). Skipped in combination with `--dry-run`. |

**`--query` examples** (API-native, fast):

```bash
# Only files modified after a date
--query "modifiedTime > '2025-01-01T00:00:00'"

# Only PDFs
--query "mimeType = 'application/pdf'"

# Only files I own
--query "'me' in owners"

# Only starred files
--query "starred = true"

# Only files shared with me
--query "sharedWithMe = true"

# Combine conditions
--query "modifiedTime > '2025-01-01' and mimeType = 'application/pdf'"
```

**`--filter` examples** (post-fetch, slower):

```bash
# Only files shared by a specific person (requires per-file permissions lookup)
--filter "shared_by:alice@company.com" --filter-confirm

# Only files larger than 10MB
--filter "size>10mb"

# Only files with comments
--filter "has:comments" --filter-confirm
```

### Workspace Export Formats

| Flag | Description |
|------|-------------|
| `--export-format TYPE=FORMAT` | Set export format for a Workspace type. Repeatable. |
| `--export-config FILE` | Load export format overrides from a YAML config file. |
| `--dual-export TYPE=FORMAT1,FORMAT2` | Export a Workspace type to multiple formats simultaneously. |

```bash
# Export Google Docs as PDF instead of docx
--export-format docs=pdf

# Export everything in a legal-friendly format
--export-format docs=pdf --export-format sheets=pdf --export-format slides=pdf

# Dual export: both Word and PDF for every Doc
--dual-export docs=docx,pdf
```

**Default export formats:**

| Google Workspace Type | Default Export | Extension |
|----------------------|---------------|-----------|
| Google Docs | Office Word | `.docx` |
| Google Sheets | Office Excel | `.xlsx` |
| Google Slides | Office PowerPoint | `.pptx` |
| Google Drawings | PDF | `.pdf` |
| Apps Script | JSON | `.json` |

Additional formats available: PDF, plain text, Markdown, EPUB, RTF, HTML, ODF, CSV, TSV, SVG, PNG. Use `gdrive-dl --list-export-formats` to see all options.

**Per-directory overrides** via `--export-config`:

```yaml
# export-config.yaml
defaults:
  docs: docx
  sheets: xlsx
  slides: pptx

overrides:
  "/Legal":
    docs: pdf
    sheets: pdf
  "/Engineering/specs":
    docs: markdown
```

### Download Control

| Flag | Description |
|------|-------------|
| `--resume` | Resume a previously interrupted download using the manifest file. |
| `--manifest FILE` | Path to the download manifest (default: `./gdrive-dl-manifest.json`). |
| `--verify` | Verify MD5 checksums after download (default: enabled for blob files). |
| `--no-verify` | Skip checksum verification. |
| `--rate-limit N` | Maximum API requests per second (default: auto-throttle within quota). |
| `--retries N` | Maximum retry attempts on transient errors (default: 5). |

### Output

| Flag | Description |
|------|-------------|
| `--report` | Generate a Markdown download report after completion. |
| `--report-format FORMAT` | Report format: `markdown` (default), `html`, or `json`. |
| `--quiet` | Suppress progress output. |
| `--verbose` | Show detailed per-file progress and API call logging. |

## Dry Run

The `--dry-run` flag traverses the directory tree and collects metadata without downloading any files:

```bash
$ gdrive-dl --dry-run https://drive.google.com/drive/folders/1ABC123xyz

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

When combined with `--permissions`, `--comments`, or `--revisions`, the dry run includes the additional API call cost for those features.

## Archival Features

### Permissions Snapshot

```bash
gdrive-dl --permissions ./backup https://drive.google.com/drive/folders/1ABC123xyz
```

Saves a `.permissions.json` sidecar file alongside each downloaded file and folder:

```json
{
  "fileId": "1ABC123xyz",
  "fileName": "Q3 Report.docx",
  "capturedAt": "2026-02-28T20:00:00Z",
  "permissions": [
    {
      "role": "owner",
      "type": "user",
      "emailAddress": "bob@company.com",
      "displayName": "Bob Smith"
    },
    {
      "role": "writer",
      "type": "user",
      "emailAddress": "alice@company.com",
      "displayName": "Alice Chen",
      "expirationTime": "2026-06-01T00:00:00Z"
    },
    {
      "role": "reader",
      "type": "anyone",
      "allowFileDiscovery": false
    }
  ]
}
```

This is particularly useful for compliance audits, employee offboarding (verifying access was removed), and organizational migrations.

### Revision History

```bash
# Download all available revisions
gdrive-dl --revisions ./backup https://drive.google.com/drive/folders/1ABC123xyz

# Download only the 3 most recent revisions per file
gdrive-dl --revisions 3 ./backup https://drive.google.com/drive/folders/1ABC123xyz
```

Revisions are saved in a `.revisions/` subdirectory alongside each file:

```
backup/
  reports/
    Q3 Report.docx                          ← current version
    Q3 Report.docx.revisions/
      2026-01-15T10:30:00Z_Q3 Report.docx   ← revision 1
      2026-02-01T14:20:00Z_Q3 Report.docx   ← revision 2
      revisions.json                         ← revision metadata
```

#### Revision History Caveats

Revision coverage varies by file type and age. Setting honest expectations:

- **Blob files** (PDFs, images, etc.): Revisions not marked "Keep Forever" are automatically purged by Google after **30 days or 100 revisions**, whichever comes first. In practice, `--revisions` on a photo library will mostly return just the current version.
- **Google Docs**: Best coverage. Google retains a richer revision history, and exporting at a specific revision ID is supported.
- **Google Sheets & Slides**: Revision export support is limited. The current implementation uses a best-effort approach; some revisions may not be exportable. This is an area of active improvement.
- **General**: Editor revisions may be merged together by Google, so the revision count may not match the number of individual edits a user made.

**Revision download is best-effort. Coverage varies by file type and age.**

### Comments Preservation

```bash
gdrive-dl --comments ./backup https://drive.google.com/drive/folders/1ABC123xyz
```

Saves a `.comments.json` sidecar for each file that has comments:

```json
{
  "fileId": "1ABC123xyz",
  "fileName": "Q3 Report.docx",
  "comments": [
    {
      "id": "comment123",
      "author": {
        "displayName": "Alice Chen",
        "emailAddress": "alice@company.com"
      },
      "content": "Should we include the APAC numbers here?",
      "createdTime": "2026-02-15T09:30:00Z",
      "resolved": true,
      "replies": [
        {
          "author": {
            "displayName": "Bob Smith",
            "emailAddress": "bob@company.com"
          },
          "content": "Yes, added in the latest revision.",
          "createdTime": "2026-02-15T11:45:00Z"
        }
      ]
    }
  ]
}
```

## Authentication

### First-Time Setup

On first run, `gdrive-dl` opens a browser window for Google OAuth consent. After granting permission, credentials are cached in `token.json` and reused automatically. Token refresh is handled transparently — subsequent runs won't open a browser unless the refresh token is revoked.

### Browser Selection

By default, `gdrive-dl` opens the system default browser for OAuth. To target a specific browser:

```bash
# Use Chrome explicitly
gdrive-dl --browser chrome https://drive.google.com/drive/folders/1ABC123xyz

# Use Firefox
gdrive-dl --browser firefox https://drive.google.com/drive/folders/1ABC123xyz
```

Chrome detection works cross-platform: via AppleScript on macOS, PATH lookup on Windows/Linux, with automatic fallback to the system default if the specified browser isn't found.

You can also set the `BROWSER` environment variable:

```bash
export BROWSER=google-chrome
gdrive-dl https://drive.google.com/drive/folders/1ABC123xyz
```

### Service Accounts

For automated/server environments where no browser is available:

```bash
gdrive-dl --service-account service-account-key.json https://drive.google.com/drive/folders/1ABC123xyz
```

Service accounts require domain-wide delegation to access user files. See [Google's service account documentation](https://developers.google.com/identity/protocols/oauth2/service-account) for setup.

### Headless Environments

In environments without a display (SSH, Docker, CI), set `--no-browser` to print the authorization URL instead of opening a browser:

```bash
gdrive-dl --no-browser https://drive.google.com/drive/folders/1ABC123xyz
# Prints: "Visit this URL to authorize: https://accounts.google.com/o/oauth2/..."
# Complete sign-in on any device, paste the code back
```

## Download Manifest

Every download session produces a manifest file (`gdrive-dl-manifest.json`) that tracks:

- File ID, name, local path, MIME type
- Download status (completed, skipped, failed, pending)
- MD5 checksum (blob files) and verification result
- Timestamps (`createdTime`, `modifiedTime` from Drive)
- File size and quota bytes used
- Sharing status and ownership

The manifest enables:

- **Resumable downloads**: Re-run with `--resume` to pick up where an interrupted session left off.
- **Incremental updates**: On re-run, `gdrive-dl` compares manifest entries against current Drive metadata and only re-downloads changed files.
- **Portable audit record**: The manifest is a complete inventory of what was downloaded, when, and from where — useful independently of the downloaded files themselves.

## Shared Drives

`gdrive-dl` handles Shared Drives (formerly Team Drives) transparently:

```bash
# Download from a specific Shared Drive folder
gdrive-dl https://drive.google.com/drive/folders/1SharedDriveFolder123

# Auto-discover and list all accessible Shared Drives
gdrive-dl --shared-drives=list

# Download from all accessible Shared Drives
gdrive-dl --shared-drives --output ./all-drives/
```

The `supportsAllDrives` and `includeItemsFromAllDrives` API parameters are set automatically on every request — you don't need to configure drive IDs manually. Files in Shared Drives that restrict downloads (`capabilities.canDownload = false`) are flagged in the dry-run report and skipped during download.

## Rate Limits & Quotas

Google Drive API enforces a quota of **12,000 queries per 60 seconds** per project (~200 requests/second). `gdrive-dl` manages this automatically:

- **Adaptive throttling**: Monitors quota usage and slows down before hitting limits.
- **Exponential backoff**: Automatically retries on `403`/`429` rate-limit errors with increasing delays and jitter.
- **Dry-run estimation**: The `--dry-run` report includes predicted API call count and estimated wall-clock time at current quota rates.
- **Manual override**: Use `--rate-limit N` to cap requests per second (useful when sharing quota with other applications).

Undocumented download bandwidth limits (~10 GB/day) may apply. If you hit `403 downloadQuotaExceeded`, the tool pauses and reports the issue — resuming the next day with `--resume` picks up where it left off.

## Comparison with Existing Tools

| Capability | rclone | PyDrive2 | Drive for Desktop | **gdrive-dl** |
|---|---|---|---|---|
| Recursive directory download | ✓ | Manual | ✓ (streaming) | ✓ |
| Permissions snapshot | ✗ | ✗ | ✗ | **✓** |
| Revision history download | ✗ | ✗ | ✗ | **✓** |
| Comments preservation | ✗ | ✗ | ✗ | **✓** |
| Rich dry-run with estimates | Basic | ✗ | ✗ | **✓** |
| Metadata-native filtering | Path only | ✗ | ✗ | **✓** (two-tier) |
| Per-directory export formats | Global only | Single | Single | **✓** |
| Dual-format Workspace export | ✗ | ✗ | ✗ | **✓** |
| Download manifest & resume | Partial | ✗ | ✗ | **✓** |
| Post-download report | ✗ | ✗ | ✗ | **✓** |
| Shared Drive auto-discovery | Manual config | ✗ | Automatic | **✓** |
| Multi-provider support | **70+ providers** | ✗ | Google only | Google only |

`gdrive-dl` trades multi-provider breadth for Google Drive depth — it's purpose-built for archival scenarios where capturing the full context of files matters more than syncing across cloud providers.

## Examples

### Compliance backup with full audit trail

```bash
gdrive-dl \
  --permissions \
  --comments \
  --metadata \
  --report \
  --output ./compliance-backup/ \
  root
```

### Employee offboarding archive

```bash
gdrive-dl \
  --permissions \
  --revisions \
  --comments \
  --query "'departing-user@company.com' in owners" \
  --report \
  --output ./offboarding/jane-doe/ \
  root
```

### Legal discovery: all PDFs modified in 2025

```bash
gdrive-dl \
  --query "mimeType='application/pdf' and modifiedTime > '2025-01-01' and modifiedTime < '2026-01-01'" \
  --revisions \
  --permissions \
  --export-format docs=pdf \
  --report \
  --output ./legal-discovery/ \
  root
```

### Selective download with dry run

```bash
# Preview what would be downloaded
gdrive-dl --dry-run \
  --query "modifiedTime > '2025-06-01'" \
  https://drive.google.com/drive/folders/1ABC123xyz

# If the dry run looks right, run it for real
gdrive-dl \
  --query "modifiedTime > '2025-06-01'" \
  --output ./recent-files/ \
  https://drive.google.com/drive/folders/1ABC123xyz
```

### Archive with legal-friendly export formats

```bash
gdrive-dl \
  --dual-export docs=docx,pdf \
  --export-format sheets=pdf \
  --export-format slides=pdf \
  --output ./archive/ \
  https://drive.google.com/drive/folders/1ABC123xyz
```

## Configuration File

For repeated use, store settings in a YAML config file:

```yaml
# gdrive-dl.yaml
credentials: ./secrets/credentials.json
token: ./secrets/token.json
browser: chrome
verify: true
report: true
report_format: markdown

export_formats:
  defaults:
    docs: docx
    sheets: xlsx
    slides: pptx
  overrides:
    "/Legal":
      docs: pdf
      sheets: pdf
    "/Engineering/specs":
      docs: markdown

archival:
  permissions: true
  comments: true
  revisions: false
  metadata: true
```

```bash
gdrive-dl --config gdrive-dl.yaml --output ./backup/ root
```

CLI flags override config file values.

## Project Structure

```
gdrive-dl/
├── gdrive_dl/
│   ├── __init__.py
│   ├── cli.py              # CLI argument parsing and entry point
│   ├── auth.py             # OAuth flow, token management, browser selection
│   ├── walker.py           # Directory traversal and metadata collection
│   ├── downloader.py       # File download and Workspace export logic
│   ├── filters.py          # Two-tier filtering (API query + post-fetch)
│   ├── manifest.py         # Download manifest read/write and resume logic
│   ├── archival.py         # Permissions, comments, revisions extraction
│   ├── report.py           # Post-download report generation
│   ├── timestamps.py       # Local file timestamp preservation
│   ├── checksums.py        # MD5 verification
│   └── config.py           # YAML config file parsing
├── tests/
├── credentials.json        # (user-provided, gitignored)
├── gdrive-dl.yaml          # (optional config)
├── pyproject.toml
├── LICENSE
└── README.md
```

## Development

```bash
git clone https://github.com/yourname/gdrive-dl.git
cd gdrive-dl
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
```

## License

MIT
