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
