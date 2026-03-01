"""Constants for gdrive-dl: MIME types, export formats, OAuth scopes, and defaults."""

from enum import Enum


class DriveType(Enum):
    """Type of Google Drive — My Drive or a Shared Drive."""

    MY_DRIVE = "my_drive"
    SHARED_DRIVE = "shared_drive"


# Google Drive MIME types
FOLDER_MIME = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

# OAuth scopes — minimum required for full download, never request write scope
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Workspace MIME → (export MIME, file extension)
EXPORT_FORMATS: dict[str, tuple[str, str]] = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
    "application/vnd.google-apps.drawing": (
        "application/pdf",
        ".pdf",
    ),
    "application/vnd.google-apps.script": (
        "application/vnd.google-apps.script+json",
        ".json",
    ),
}

# Web export URL templates for large Workspace files (>10 MB exportSizeLimitExceeded).
# Used as final fallback when both files.export() and exportLinks fail.
# Format string takes {file_id} and {fmt} (file extension without dot).
WEB_EXPORT_URLS: dict[str, str] = {
    "application/vnd.google-apps.document": (
        "https://docs.google.com/document/d/{file_id}/export?format={fmt}"
    ),
    "application/vnd.google-apps.spreadsheet": (
        "https://docs.google.com/spreadsheets/d/{file_id}/export?format={fmt}"
    ),
    "application/vnd.google-apps.presentation": (
        "https://docs.google.com/presentation/d/{file_id}/export/{fmt}"
    ),
    "application/vnd.google-apps.drawing": (
        "https://docs.google.com/drawings/d/{file_id}/export/{fmt}"
    ),
}

# Extension used in web export URLs, keyed by export MIME type
_WEB_EXPORT_FMT: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/pdf": "pdf",
}

# Types that cannot be downloaded or exported
NON_DOWNLOADABLE: frozenset[str] = frozenset(
    {
        "application/vnd.google-apps.form",
        "application/vnd.google-apps.site",
        "application/vnd.google-apps.map",
        "application/vnd.google-apps.fusiontable",
        FOLDER_MIME,
        SHORTCUT_MIME,
        "application/vnd.google-apps.drive-sdk",
    }
)

# API defaults
DEFAULT_PAGE_SIZE = 1000
DEFAULT_RETRIES = 5
DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024  # 5 MB — must be multiple of 256 KB
