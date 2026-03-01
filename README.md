# gdrive-dl

Google Drive archival CLI that downloads files with full context preservation — permissions, comments, revision history, and metadata.

Unlike Google Takeout or Drive for Desktop, gdrive-dl preserves the audit trail: who has access, what changed, and when. Designed for compliance backups, employee offboarding, legal discovery, and resumable bulk downloads.

## Features

- **Full archival** — permissions snapshots, comment threads, revision history, and metadata as JSON sidecar files
- **Resumable downloads** — manifest tracks progress; interrupted sessions resume where they left off
- **Two-tier filtering** — API-level query pushdown (`--query`) and post-fetch predicates (`--filter`)
- **Shared with me** — download files shared by others via `--shared-with-me`, even if not in your folder tree
- **Workspace export** — Google Docs/Sheets/Slides/Drawings exported to Office or PDF formats, with per-directory overrides
- **Dry-run preview** — see file counts, sizes by type, and estimated API calls before downloading
- **Adaptive rate limiting** — automatic throttle adjustment with exponential backoff on rate-limit errors
- **Checksum verification** — MD5 verification for downloaded blob files
- **Timestamp preservation** — local files retain their original Drive modification and creation times
- **Post-download reports** — Markdown, HTML, or JSON summaries of completed, skipped, and failed files

## Quick Start

### Prerequisites

- Python 3.9+
- A Google Cloud project with the Drive API enabled
- OAuth 2.0 Desktop credentials (`credentials.json`) from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)

### Install

```bash
git clone https://github.com/aetherrecur/google-dl.git
cd google-dl
pip install -e .
```

### First Run

```bash
gdrive-dl root                                          # download entire My Drive
gdrive-dl https://drive.google.com/drive/folders/1ABC   # download a specific folder
gdrive-dl --dry-run root                                # preview without downloading
```

On first run, a browser window opens for OAuth consent (read-only scope: `drive.readonly`). The token is cached to `./token.json` for subsequent runs.

## Usage

```
gdrive-dl [OPTIONS] SOURCE
```

`SOURCE` accepts three forms:

| Form | Example |
|------|---------|
| Folder URL | `https://drive.google.com/drive/folders/1ABC123xyz` |
| Folder ID | `1ABC123xyz` |
| My Drive root | `root` |

## CLI Reference

### Core

| Flag | Default | Description |
|------|---------|-------------|
| `--dry-run` | off | Preview what would be downloaded (no files written) |
| `-o, --output DIR` | `./<folder_name>/` | Output directory |
| `--config FILE` | auto-discovered | YAML config file path |
| `--version` | | Show version and exit |

### Authentication

| Flag | Default | Description |
|------|---------|-------------|
| `--credentials FILE` | `./credentials.json` | OAuth 2.0 client secrets JSON |
| `--token FILE` | `./token.json` | Cached OAuth token (created automatically) |
| `--service-account FILE` | | Service account key JSON (headless/server use) |
| `--browser NAME` | system default | Browser for OAuth sign-in (`chrome`, `firefox`, `auto`) |
| `--no-browser` | off | Print authorization URL instead of opening browser |

### Filtering

| Flag | Description |
|------|-------------|
| `--query EXPR` | API-level filter using [Google Drive query syntax](https://developers.google.com/drive/api/guides/ref-search-terms). Evaluated server-side, reduces API calls |
| `--filter EXPR` | Post-fetch filter (see [Filter Syntax](#filter-syntax) below). Multiple predicates comma-separated, ANDed together |
| `--filter-confirm` | Required when post-fetch filter would exceed 100 additional API calls |

### Shared Files

| Flag | Description |
|------|-------------|
| `--shared-with-me` | Query the "Shared with me" virtual collection directly (flat, no folder tree walk) |
| `--shared-drives[=list]` | Include Shared Drives. Use `=list` for interactive selection |

### Archival

| Flag | Description |
|------|-------------|
| `--permissions` | Save permissions as `.permissions.json` sidecar per file/folder |
| `--comments` | Save comment threads as `.comments.json` sidecar per file |
| `--metadata` | Save Drive metadata as `.metadata.json` sidecar per file/folder |
| `--revisions [N]` | Download revision history into `.revisions/` subdirectory. No value = all, N = N most recent |

### Export & Download

| Flag | Default | Description |
|------|---------|-------------|
| `--export-format TYPE=FMT` | | Override Workspace export format (e.g., `docs=pdf`). Repeatable |
| `--rate-limit N` | adaptive | Fixed API rate limit (req/sec). Disables adaptive throttle |
| `--retries N` | `5` | Max retries per API call on transient errors |
| `--no-verify` | off | Skip MD5 checksum verification after download |

### Reporting

| Flag | Default | Description |
|------|---------|-------------|
| `--report` | off | Generate download report after completion |
| `--report-format FMT` | `markdown` | Report format: `markdown`, `html`, or `json` |

## Filter Syntax

The `--filter` flag accepts comma-separated predicates. All predicates are ANDed together. Folders are always kept regardless of filter.

| Predicate | Example | Description |
|-----------|---------|-------------|
| `size>N` | `size>10mb` | File size comparison (`>`, `<`, `>=`, `<=`). Units: `b`, `kb`, `mb`, `gb` (SI). Workspace files with unknown size are excluded |
| `ext:EXT` | `ext:.pdf` | File extension match (case-insensitive, leading dot optional) |
| `name:PATTERN` | `name:report` | Filename substring match (case-insensitive) |
| `modified_before:DATE` | `modified_before:2025-01-01` | Files modified before date (YYYY-MM-DD) |
| `modified_after:DATE` | `modified_after:2024-06-01` | Files modified after date (YYYY-MM-DD) |
| `shared:BOOL` | `shared:true` | Filter by shared status (`true` or `false`) |

### `--shared-with-me` vs. `--filter "shared:true"`

These are different:

| | `--shared-with-me` | `--filter "shared:true"` |
|---|---|---|
| Queries | The "Shared with me" virtual collection | Your folder tree, then filters |
| Finds | Files others shared with you (not in your Drive) | Files in your Drive that have been shared |
| Tree walk | No (flat query) | Yes (full BFS traversal) |

## Workspace Export Formats

Google Workspace files are exported on download. Default formats:

| Workspace Type | Default Export | Extension |
|---------------|---------------|-----------|
| Google Docs | Office Open XML | `.docx` |
| Google Sheets | Office Open XML | `.xlsx` |
| Google Slides | Office Open XML | `.pptx` |
| Google Drawings | PDF | `.pdf` |
| Apps Script | JSON | `.json` |

Override with `--export-format TYPE=FORMAT` (e.g., `--export-format docs=pdf`).

For large Workspace files exceeding the 10 MB API export limit, the tool automatically falls back to `exportLinks` and then web export URLs.

### Non-Downloadable Types (skipped automatically)

Google Forms, Google Sites, Google My Maps, Fusion Tables, and third-party Drive SDK files cannot be exported and are reported in dry-run output.

## Examples

```bash
# Dry-run preview of entire Drive
gdrive-dl --dry-run root

# Download a specific folder with archival
gdrive-dl --permissions --comments --revisions \
  https://drive.google.com/drive/folders/1ABC123xyz

# Download only PDFs and Google Docs under 50 MB
gdrive-dl \
  --query "mimeType = 'application/pdf' or mimeType = 'application/vnd.google-apps.document'" \
  --filter "size<50mb" root

# Download files shared with you, excluding zips and videos
gdrive-dl --shared-with-me \
  --query "not mimeType = 'application/zip' and not mimeType = 'video/mp4'" \
  -o ./shared root

# Filter to recently modified files in your Drive
gdrive-dl --filter "modified_after:2024-01-01,ext:.pdf" root

# Export Google Docs as PDF, Sheets as CSV
gdrive-dl --export-format docs=pdf --export-format sheets=csv root

# Full archival with HTML report
gdrive-dl --permissions --comments --metadata --revisions \
  --report --report-format html -o ./backup root

# Headless server with service account
gdrive-dl --service-account ./sa-key.json -o ./archive root
```

## Configuration

YAML config files are auto-discovered in this order:

1. `./gdrive-dl.yaml` or `./gdrive-dl.yml`
2. `$XDG_CONFIG_HOME/gdrive-dl/config.yaml`
3. `~/.config/gdrive-dl/config.yaml`
4. `~/.gdrive-dl.yaml`
5. `~/Library/Application Support/gdrive-dl/config.yaml` (macOS)

Or specify explicitly with `--config PATH`.

```yaml
# Global export format defaults
export_formats:
  defaults:
    docs: pdf
    sheets: xlsx
    slides: pptx

  # Per-directory overrides (longest prefix match wins)
  overrides:
    Legal/:
      docs: pdf
      sheets: pdf
    Engineering/:
      docs: docx

# CLI defaults (overridden by command-line flags)
dry_run: false
retries: 5
permissions: true
comments: true
```

## Resume

Downloads are tracked in a `gdrive-dl-manifest.json` file in the output directory. If a download is interrupted (Ctrl-C, network failure, etc.), re-running the same command resumes from where it left off. Only files that have changed since the last successful download are re-fetched.

The manifest is flushed every 10 files or 30 seconds, and immediately on `SIGINT`/`SIGTERM`.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All files downloaded successfully |
| `1` | Partial failure (some files failed or had checksum mismatches) |
| `130` | Interrupted by SIGINT (Ctrl-C) |
| `143` | Interrupted by SIGTERM |

## Project Structure

```
src/gdrive_dl/
├── cli.py          # Click CLI entry point and option definitions
├── runner.py       # Download pipeline orchestration
├── walker.py       # BFS folder traversal and DriveItem dataclass
├── downloader.py   # File download and Workspace export logic
├── filters.py      # API query building and post-fetch predicates
├── archival.py     # Permissions, comments, metadata, revision sidecars
├── manifest.py     # Download manifest for resume support
├── auth.py         # OAuth 2.0 and service account authentication
├── config.py       # YAML config loading and export format overrides
├── report.py       # Dry-run and post-download report generation
├── throttle.py     # Adaptive rate limiting with token bucket
├── checksums.py    # MD5 checksum verification
├── timestamps.py   # File timestamp restoration
├── constants.py    # MIME types, export formats, API defaults
└── exceptions.py   # Custom exception hierarchy
```

## Development

```bash
pip install -e ".[dev]"
pytest                    # run tests with coverage
ruff check .              # lint
mypy src/                 # type check (strict mode)
```

## License

MIT

See [docs/product-spec.md](docs/product-spec.md) for the full product specification.
