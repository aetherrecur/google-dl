# gdrive-dl

Google Drive archival CLI — downloads files, permissions, comments, and revision history.

## Quick Start

```bash
pip install -e .
gdrive-dl root                     # download entire My Drive
gdrive-dl <folder-url-or-id>       # download a specific folder
```

## Usage

```
gdrive-dl [OPTIONS] SOURCE
```

`SOURCE` is a Google Drive folder URL, folder ID, or `root` for My Drive.

### Core Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview what would be downloaded (no files written) |
| `-o, --output DIR` | Output directory (default: `./<folder_name>/`) |
| `--config FILE` | YAML config file (auto-discovered if not provided) |

### Authentication

| Flag | Description |
|------|-------------|
| `--credentials FILE` | OAuth credentials JSON (default: `./credentials.json`) |
| `--token FILE` | Cached token file (default: `./token.json`) |
| `--service-account FILE` | Use service account key instead of OAuth |
| `--browser NAME` | Browser for OAuth sign-in (chrome, firefox, auto) |
| `--no-browser` | Print authorization URL instead of opening browser |

### Filtering

| Flag | Description |
|------|-------------|
| `--query EXPR` | API-level filter using Google Drive query syntax |
| `--filter EXPR` | Post-fetch filter: `size>10mb`, `ext:.pdf`, `name:report`, `modified_before:2025-01-01`, `modified_after:2025-01-01`, `shared:true` |
| `--filter-confirm` | Allow expensive filter operations (>100 API calls) |
| `--shared-with-me` | Query the "Shared with me" collection instead of walking a folder tree |
| `--shared-drives[=list]` | Include Shared Drives; use `=list` to select interactively |

### Archival

| Flag | Description |
|------|-------------|
| `--permissions` | Save permissions manifest per file |
| `--comments` | Export comments as sidecar JSON files |
| `--metadata` | Save full Drive metadata as sidecar JSON |
| `--revisions [N]` | Download revision history (no value = all, N = N most recent) |

### Export & Download

| Flag | Description |
|------|-------------|
| `--export-format TYPE=FMT` | Export format override (e.g., `docs=pdf`). Repeatable |
| `--rate-limit N` | Fixed API rate limit (req/sec); disables adaptive throttle |
| `--retries N` | Max retries per API call (default: 5) |
| `--no-verify` | Skip MD5 checksum verification after download |

### Reporting

| Flag | Description |
|------|-------------|
| `--report` | Generate download report after completion |
| `--report-format FMT` | Report format: `markdown`, `html`, or `json` (default: markdown) |

## Examples

```bash
# Dry-run preview of entire Drive
gdrive-dl --dry-run root

# Download a specific folder
gdrive-dl https://drive.google.com/drive/folders/1ABC123xyz

# Download only PDFs and Google Docs under 50 MB
gdrive-dl --query "mimeType = 'application/pdf' or mimeType = 'application/vnd.google-apps.document'" \
  --filter "size<50mb" root

# Download files shared with you (not in your folder tree)
gdrive-dl --shared-with-me -o ./shared root

# Download shared files, excluding zips and videos
gdrive-dl --shared-with-me \
  --query "not mimeType = 'application/zip' and not mimeType = 'video/mp4'" \
  -o ./shared root

# Filter to only shared files within your Drive tree
gdrive-dl --filter "shared:true" root

# Full archival with permissions, comments, and revisions
gdrive-dl --permissions --comments --revisions --report root

# Export Google Docs as PDF, Sheets as XLSX
gdrive-dl --export-format docs=pdf --export-format sheets=xlsx root
```

## Configuration

Optional YAML config file (`gdrive-dl.yaml` or `.gdrive-dl.yaml`, auto-discovered):

```yaml
export_formats:
  docs: pdf
  sheets: xlsx

overrides:
  "/Legal":
    docs: pdf
```

See [docs/product-spec.md](docs/product-spec.md) for full documentation.
