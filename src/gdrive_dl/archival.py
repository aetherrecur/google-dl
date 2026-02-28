"""Archival features: permissions, comments, metadata, and revision history."""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from googleapiclient.http import MediaIoBaseDownload

from gdrive_dl.throttle import TokenBucketThrottler, throttled_execute

if TYPE_CHECKING:
    from gdrive_dl.walker import DriveItem

logger = logging.getLogger(__name__)

_PERMISSIONS_FIELDS = (
    "permissions(id,type,role,emailAddress,displayName,domain,"
    "expirationTime,allowFileDiscovery,deleted,pendingOwner,"
    "permissionDetails(permissionType,role,inherited,inheritedFrom))"
)

_COMMENTS_FIELDS = (
    "comments(id,author(displayName,emailAddress),content,"
    "createdTime,modifiedTime,resolved,anchor,replies("
    "author(displayName,emailAddress),content,createdTime,modifiedTime))"
)

_REVISIONS_FIELDS = (
    "revisions(id,modifiedTime,mimeType,keepForever,"
    "originalFilename,size,exportLinks)"
)


def _sidecar_path(
    item: DriveItem, output_dir: Path, suffix: str,
) -> Path:
    """Compute sidecar file path for a DriveItem."""
    if item.is_folder:
        return output_dir / item.drive_path / f".folder.{suffix}"
    return output_dir / f"{item.drive_path}.{suffix}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def save_permissions(
    service: Any,
    item: DriveItem,
    output_dir: Path,
    throttler: TokenBucketThrottler,
) -> None:
    """Fetch and save permissions sidecar. Best-effort — never raises."""
    try:
        request = service.permissions().list(
            fileId=item.id,
            supportsAllDrives=True,
            fields=_PERMISSIONS_FIELDS,
        )
        response = throttled_execute(request, throttler)
        permissions = response.get("permissions", [])

        # Count direct vs inherited
        direct = 0
        inherited = 0
        for perm in permissions:
            details = perm.get("permissionDetails", [])
            if any(d.get("inherited") for d in details):
                inherited += 1
            else:
                direct += 1

        sidecar = {
            "fileId": item.id,
            "fileName": item.name,
            "capturedAt": _now_iso(),
            "permissions": permissions,
            "summary": {
                "directPermissions": direct,
                "inheritedPermissions": inherited,
            },
        }

        path = _sidecar_path(item, output_dir, "permissions.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))
        logger.debug("Saved permissions for %s", item.name)

    except Exception as exc:
        logger.warning("Failed to save permissions for %s: %s", item.name, exc)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def save_comments(
    service: Any,
    item: DriveItem,
    output_dir: Path,
    throttler: TokenBucketThrottler,
) -> None:
    """Fetch and save comments sidecar. Best-effort — never raises."""
    try:
        request = service.comments().list(
            fileId=item.id,
            fields=_COMMENTS_FIELDS,
            includeDeleted=False,
        )
        response = throttled_execute(request, throttler)
        comments = response.get("comments", [])

        sidecar = {
            "fileId": item.id,
            "fileName": item.name,
            "capturedAt": _now_iso(),
            "commentCount": len(comments),
            "comments": comments,
        }

        path = _sidecar_path(item, output_dir, "comments.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))
        logger.debug("Saved %d comments for %s", len(comments), item.name)

    except Exception as exc:
        logger.warning("Failed to save comments for %s: %s", item.name, exc)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def save_metadata(item: DriveItem, output_dir: Path) -> None:
    """Serialize DriveItem fields to metadata sidecar. No API calls."""
    try:
        sidecar = {
            "id": item.id,
            "name": item.name,
            "mimeType": item.mime_type,
            "size": item.size,
            "md5Checksum": item.md5_checksum,
            "createdTime": item.created_time,
            "modifiedTime": item.modified_time,
            "parents": item.parents,
            "drivePath": item.drive_path,
            "isFolder": item.is_folder,
            "canDownload": item.can_download,
            "isShortcut": item.is_shortcut,
            "shortcutTargetId": item.shortcut_target_id,
            "sharedDriveId": item.shared_drive_id,
            "isWorkspaceFile": item.is_workspace_file,
        }

        path = _sidecar_path(item, output_dir, "metadata.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False))
        logger.debug("Saved metadata for %s", item.name)

    except Exception as exc:
        logger.warning("Failed to save metadata for %s: %s", item.name, exc)


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------


def _safe_timestamp(ts: str) -> str:
    """Make a timestamp safe for filenames by replacing colons."""
    return ts.replace(":", "-")


def save_revisions(
    service: Any,
    item: DriveItem,
    output_dir: Path,
    throttler: TokenBucketThrottler,
    creds: Any | None = None,
    revision_count: int | None = None,
) -> None:
    """List and optionally download revision history. Best-effort — never raises."""
    try:
        request = service.revisions().list(
            fileId=item.id,
            fields=_REVISIONS_FIELDS,
            supportsAllDrives=True,
        )
        response = throttled_execute(request, throttler)
        revisions = response.get("revisions", [])

        # Apply revision_count limit (last N)
        if (revision_count is not None) and (revision_count > 0):
            revisions = revisions[-revision_count:]

        # Create .revisions/ directory
        rev_dir = output_dir / f"{item.drive_path}.revisions"
        rev_dir.mkdir(parents=True, exist_ok=True)

        # Write metadata
        meta = {
            "fileId": item.id,
            "fileName": item.name,
            "capturedAt": _now_iso(),
            "revisionCount": len(revisions),
            "revisions": revisions,
        }
        (rev_dir / "revisions.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
        )

        # Download revisions
        for rev in revisions:
            _download_revision(service, item, rev, rev_dir, throttler, creds)

        logger.debug("Saved %d revisions for %s", len(revisions), item.name)

    except Exception as exc:
        logger.warning("Failed to save revisions for %s: %s", item.name, exc)


def _download_revision(
    service: Any,
    item: DriveItem,
    rev: dict[str, Any],
    rev_dir: Path,
    throttler: TokenBucketThrottler,
    creds: Any | None,
) -> None:
    """Download a single revision file. Best-effort."""
    rev_id = rev.get("id", "unknown")
    modified = rev.get("modifiedTime", "unknown")
    safe_ts = _safe_timestamp(modified)
    filename = rev.get("originalFilename", item.name)
    dest_name = f"{safe_ts}_{rev_id}_{filename}"
    dest_path = rev_dir / dest_name

    try:
        # Blob revisions: only downloadable if keepForever is True
        if rev.get("keepForever"):
            throttler.acquire()
            request = service.revisions().get_media(
                fileId=item.id, revisionId=rev_id,
                supportsAllDrives=True,
            )
            fh = io.FileIO(str(dest_path), "wb")
            dl = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _status, done = dl.next_chunk()
            fh.close()
            logger.debug("Downloaded revision %s for %s", rev_id, item.name)
            return

        # Workspace revisions: use exportLinks if available
        export_links = rev.get("exportLinks")
        if export_links and creds and hasattr(creds, "token"):
            import requests

            from gdrive_dl.constants import EXPORT_FORMATS

            format_entry = EXPORT_FORMATS.get(item.mime_type)
            if format_entry is None:
                return
            export_mime = format_entry[0]
            url = export_links.get(export_mime)
            if not url:
                return

            throttler.acquire()
            headers = {"Authorization": f"Bearer {creds.token}"}
            with requests.get(url, headers=headers, stream=True, timeout=300) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=5 * 1024 * 1024):
                        f.write(chunk)
            logger.debug(
                "Downloaded workspace revision %s for %s", rev_id, item.name,
            )

    except Exception as exc:
        logger.warning(
            "Failed to download revision %s for %s: %s", rev_id, item.name, exc,
        )
        # Clean up partial
        try:
            if dest_path.exists():
                dest_path.unlink()
        except OSError:
            pass
