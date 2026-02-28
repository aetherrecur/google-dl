"""Authentication module for gdrive-dl.

Handles OAuth2 desktop flow, service account authentication, token caching,
browser selection, and post-auth Drive metadata display.
"""

import json
import logging
import os
import re
import webbrowser
from pathlib import Path
from typing import Any, Optional

from google.auth.credentials import Credentials as BaseCredentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from gdrive_dl.constants import SCOPES
from gdrive_dl.exceptions import AuthError, SourceNotFoundError

logger = logging.getLogger(__name__)

# Pattern for Drive folder URLs
_FOLDER_URL_PATTERN = re.compile(
    r"https?://drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)"
)


def build_drive_service(
    credentials_file: str,
    token_file: str,
    service_account_file: Optional[str] = None,
    browser: Optional[str] = None,
    no_browser: bool = False,
) -> Resource:
    """Authenticate and return a Drive API v3 service object.

    Args:
        credentials_file: Path to OAuth client secrets JSON.
        token_file: Path to cached token JSON.
        service_account_file: Optional path to service account key file.
        browser: Browser name for OAuth flow (None for system default).
        no_browser: If True, print URL instead of opening browser.

    Returns:
        Authorized Drive API v3 Resource.

    Raises:
        AuthError: On authentication failure.
    """
    if service_account_file:
        creds: BaseCredentials = _authenticate_service_account(service_account_file, SCOPES)
    else:
        creds = _authenticate_oauth(credentials_file, token_file, browser, no_browser)

    return build("drive", "v3", credentials=creds)


def _authenticate_oauth(
    credentials_file: str,
    token_file: str,
    browser: Optional[str],
    no_browser: bool,
) -> Credentials:
    """Run OAuth2 flow: load cached token → refresh → browser flow.

    Args:
        credentials_file: Path to OAuth client secrets JSON.
        token_file: Path to cached token JSON.
        browser: Browser name for OAuth flow.
        no_browser: If True, print URL instead of opening browser.

    Returns:
        Valid OAuth2 Credentials.

    Raises:
        AuthError: On authentication failure.
    """
    creds: Optional[Credentials] = None
    token_path = Path(token_file)

    # Step 1: Try loading cached token
    if token_path.exists():
        try:
            token_data = json.loads(token_path.read_text())
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)  # type: ignore[no-untyped-call]
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.warning("Could not load cached token: %s", exc)
            creds = None

    # Step 2: Check scope sufficiency
    if (creds is not None) and (not _scopes_sufficient(creds.scopes, SCOPES)):
        logger.warning("Cached token has insufficient scopes — re-authenticating.")
        token_path.unlink(missing_ok=True)
        creds = None

    # Step 3: Try silent refresh
    if (creds is not None) and (creds.expired) and (creds.refresh_token):
        try:
            creds.refresh(Request())  # type: ignore[no-untyped-call]
        except Exception as exc:
            logger.warning("Token refresh failed: %s — will re-authenticate.", exc)
            token_path.unlink(missing_ok=True)
            creds = None

    # Step 4: If still no valid creds, run browser flow
    if (creds is None) or (not creds.valid):
        creds = _run_browser_flow(credentials_file, browser, no_browser)
        _save_token(creds, token_file)

    return creds


def _run_browser_flow(
    credentials_file: str,
    browser: Optional[str],
    no_browser: bool,
) -> Credentials:
    """Launch the OAuth browser flow.

    Args:
        credentials_file: Path to OAuth client secrets JSON.
        browser: Browser name for OAuth flow.
        no_browser: If True, print URL instead of opening browser.

    Returns:
        Fresh OAuth2 Credentials.

    Raises:
        AuthError: If credentials file is missing or flow fails.
    """
    creds_path = Path(credentials_file)
    if not creds_path.exists():
        raise AuthError(
            f"Credentials file not found: {credentials_file}\n"
            "Download OAuth 2.0 Client ID credentials (Desktop app type) from:\n"
            "  https://console.cloud.google.com/apis/credentials\n"
            "Save the JSON file as 'credentials.json' in your working directory."
        )

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
        browser_name = _resolve_browser(browser)
        creds = flow.run_local_server(
            port=0,
            browser=browser_name,
            open_browser=not no_browser,
            timeout_seconds=180,
        )
    except Exception as exc:
        raise AuthError(f"OAuth authentication failed: {exc}") from exc

    return creds  # type: ignore[no-any-return]


def _authenticate_service_account(
    key_file: str,
    scopes: list[str],
    subject_email: Optional[str] = None,
) -> BaseCredentials:
    """Load service account credentials.

    Args:
        key_file: Path to service account key JSON.
        scopes: OAuth scopes to request.
        subject_email: Optional email for domain-wide delegation.

    Returns:
        Service account Credentials.

    Raises:
        AuthError: If key file is missing or invalid.
    """
    key_path = Path(key_file)
    if not key_path.exists():
        raise AuthError(f"Service account key file not found: {key_file}")

    try:
        creds = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            str(key_path), scopes=scopes
        )
        if subject_email:
            creds = creds.with_subject(subject_email)
        return creds  # type: ignore[no-any-return]
    except Exception as exc:
        raise AuthError(f"Failed to load service account credentials: {exc}") from exc


def _scopes_sufficient(
    cached_scopes: Optional[list[str]],
    required: list[str],
) -> bool:
    """Check if cached token scopes cover the required scopes.

    Args:
        cached_scopes: Scopes from the cached token (may be None).
        required: Required scopes.

    Returns:
        True if cached_scopes is a superset of required.
    """
    if not cached_scopes:
        return False
    return set(required).issubset(set(cached_scopes))


def _resolve_browser(browser_arg: Optional[str]) -> Optional[str]:
    """Resolve browser name for webbrowser module.

    Args:
        browser_arg: User-provided browser name, 'auto', or None.

    Returns:
        webbrowser-compatible browser name, or None for system default.
    """
    # Check BROWSER env var when no explicit arg
    if browser_arg is None:
        env_browser = os.environ.get("BROWSER")
        if env_browser:
            return env_browser
        return None

    if browser_arg == "auto":
        try:
            webbrowser.get("chrome")
            return "chrome"
        except Exception:
            pass
        return None

    # Explicit browser name (chrome, firefox, etc.)
    return browser_arg


def _save_token(creds: Credentials, token_file: str) -> None:
    """Save OAuth token to file with restricted permissions (0o600).

    Args:
        creds: OAuth2 credentials to save.
        token_file: Path to write the token JSON.
    """
    token_path = Path(token_file)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())  # type: ignore[no-untyped-call]
    os.chmod(str(token_path), 0o600)


def get_drive_about(service: Resource) -> dict[str, Any]:
    """Fetch user info and storage quota via about.get.

    Validates that auth and scopes are working with a single lightweight API call.

    Args:
        service: Authorized Drive API v3 Resource.

    Returns:
        Dict with 'user' and 'storageQuota' keys.

    Raises:
        AuthError: If the API call fails.
    """
    try:
        result: dict[str, Any] = (
            service.about()
            .get(
                fields="user(displayName,emailAddress,photoLink),"
                "storageQuota(limit,usage,usageInDrive,usageInDriveTrash)"
            )
            .execute()
        )
        return result
    except Exception as exc:
        raise AuthError(
            f"Authentication succeeded but API access failed: {exc}"
        ) from exc


def format_drive_about(about: dict[str, Any]) -> str:
    """Format Drive about info for display.

    Args:
        about: Dict from get_drive_about().

    Returns:
        Human-readable string with user and storage info.
    """
    user = about.get("user", {})
    email = user.get("emailAddress", "unknown")
    display_name = user.get("displayName", "")
    quota = about.get("storageQuota", {})

    lines = []

    name_part = f" ({display_name})" if display_name else ""
    lines.append(f"Authenticated as: {email}{name_part}")

    usage = int(quota.get("usage", 0))
    limit = quota.get("limit")
    drive_usage = int(quota.get("usageInDrive", 0))
    trash_usage = int(quota.get("usageInDriveTrash", 0))

    if limit is not None:
        limit_int = int(limit)
        pct = (usage / limit_int * 100) if (limit_int > 0) else 0
        lines.append(
            f"Drive storage:  {_format_bytes(usage)} / {_format_bytes(limit_int)} "
            f"used ({pct:.1f}%)"
        )
    else:
        lines.append(f"Drive storage:  {_format_bytes(usage)} used (Unlimited quota)")

    lines.append(f"  Drive files:  {_format_bytes(drive_usage)}")
    lines.append(f"  Trash:        {_format_bytes(trash_usage)} (recoverable)")

    return "\n".join(lines)


def extract_folder_id(source: str) -> str:
    """Extract folder ID from URL, raw ID, or 'root' keyword.

    Args:
        source: Drive folder URL, folder ID, or 'root'.

    Returns:
        The folder ID string.

    Raises:
        SourceNotFoundError: If the source cannot be parsed.
    """
    if not source:
        raise SourceNotFoundError("Source cannot be empty.")

    # Handle 'root' keyword
    if source == "root":
        return "root"

    # Try URL pattern
    match = _FOLDER_URL_PATTERN.search(source)
    if match:
        return match.group(1)

    # If it looks like a URL but didn't match, it's invalid
    if source.startswith("http://") or source.startswith("https://"):
        raise SourceNotFoundError(
            f"Could not extract folder ID from URL: {source}\n"
            "Expected format: https://drive.google.com/drive/folders/<FOLDER_ID>"
        )

    # Assume raw folder ID — must be alphanumeric with hyphens/underscores
    if re.match(r"^[a-zA-Z0-9_-]+$", source):
        return source

    raise SourceNotFoundError(f"Could not extract folder ID from: {source}")


def verify_source_folder(service: Resource, folder_id: str) -> dict[str, Any]:
    """Verify that the source folder exists and is accessible.

    Args:
        service: Authorized Drive API v3 Resource.
        folder_id: The folder ID to verify.

    Returns:
        Folder metadata dict.

    Raises:
        SourceNotFoundError: If the folder doesn't exist or isn't accessible.
    """
    try:
        result: dict[str, Any] = (
            service.files()
            .get(
                fileId=folder_id,
                fields="id,name,mimeType,driveId",
                supportsAllDrives=True,
            )
            .execute()
        )
        return result
    except Exception as exc:
        raise SourceNotFoundError(
            f"Folder not found or not accessible: {folder_id}\n"
            f"Error: {exc}"
        ) from exc


def _format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string (e.g., '12.4 GB')."""
    if num_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    unit_index = 0

    while (size >= 1024) and (unit_index < len(units) - 1):
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} B"
    return f"{size:.1f} {units[unit_index]}"
