"""BFS traversal of Google Drive folder trees, producing DriveItem instances."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from googleapiclient.discovery import Resource

from gdrive_dl.constants import DEFAULT_PAGE_SIZE, FOLDER_MIME, SHORTCUT_MIME, DriveType
from gdrive_dl.filters import build_query
from gdrive_dl.throttle import TokenBucketThrottler, throttled_execute

logger = logging.getLogger(__name__)

# Fields requested on every files.list call
_LIST_FIELDS = (
    "nextPageToken,"
    "files("
    "id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,"
    "parents,md5Checksum,sha256Checksum,trashed,driveId,shared,ownedByMe,"
    "capabilities/canDownload,"
    "shortcutDetails/targetId,shortcutDetails/targetMimeType,"
    "shortcutDetails/targetResourceKey,"
    "exportLinks"
    ")"
)

# Fields for a single file get (shortcut resolution)
_GET_FIELDS = (
    "id,name,mimeType,size,quotaBytesUsed,createdTime,modifiedTime,"
    "parents,md5Checksum,sha256Checksum,trashed,driveId,shared,ownedByMe,"
    "capabilities/canDownload,"
    "shortcutDetails/targetId,shortcutDetails/targetMimeType,"
    "shortcutDetails/targetResourceKey,"
    "exportLinks"
)

_SHARED_DRIVE_KWARGS: dict[str, Any] = {
    "supportsAllDrives": True,
    "includeItemsFromAllDrives": True,
}


@dataclass
class DriveContext:
    """Encapsulates whether a folder lives in My Drive or a Shared Drive.

    Provides kwargs helpers to inject the correct parameters into API calls.
    """

    drive_type: DriveType
    drive_id: str | None

    def list_kwargs(self) -> dict[str, Any]:
        """Return kwargs for files.list API calls."""
        kwargs: dict[str, Any] = {
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if self.drive_type == DriveType.SHARED_DRIVE:
            kwargs["corpora"] = "drive"
            kwargs["driveId"] = self.drive_id
        return kwargs

    def get_kwargs(self) -> dict[str, Any]:
        """Return kwargs for files.get / get_media API calls."""
        return {"supportsAllDrives": True}


@dataclass
class DriveItem:
    """A single Drive file or folder, ready for download decisions."""

    id: str
    name: str
    mime_type: str
    size: int | None
    md5_checksum: str | None
    created_time: str
    modified_time: str
    parents: list[str]
    drive_path: str
    is_folder: bool
    can_download: bool
    is_shortcut: bool
    shortcut_target_id: str | None
    shared_drive_id: str | None

    @property
    def is_workspace_file(self) -> bool:
        """True for exportable application/vnd.google-apps.* types (not folder/shortcut)."""
        return (
            self.mime_type.startswith("application/vnd.google-apps.")
            and (not self.is_folder)
            and (not self.is_shortcut)
        )


def walk(
    service: Resource,
    root_folder_id: str,
    throttler: TokenBucketThrottler | None = None,
    extra_query: str | None = None,
) -> list[DriveItem]:
    """BFS traversal returning a flat list of all DriveItems under root_folder_id.

    Folders are included (is_folder=True) to support directory creation and
    bottom-up timestamp application. Shortcuts are resolved to their targets.
    Cycle detection via visited_ids prevents infinite loops.
    """
    all_items: list[DriveItem] = []
    visited_ids: set[str] = {root_folder_id}
    queue: deque[tuple[str, Path]] = deque([(root_folder_id, Path())])

    while queue:
        folder_id, local_base = queue.popleft()
        folder_items = _list_folder_all_pages(
            service, folder_id, throttler, extra_query,
        )
        deduped = _deduplicate_names(folder_items)

        for raw_item in deduped:
            # Resolve shortcuts
            if raw_item.get("mimeType") == SHORTCUT_MIME:
                resolved = _resolve_shortcut(
                    service, raw_item, visited_ids, throttler,
                )
                if resolved is None:
                    continue
                raw_item = resolved

            node = _build_drive_item(raw_item, local_base)
            all_items.append(node)

            if node.is_folder and (node.id not in visited_ids):
                visited_ids.add(node.id)
                queue.append((node.id, local_base / node.name))

    return all_items


def _list_folder_all_pages(
    service: Resource,
    folder_id: str,
    throttler: TokenBucketThrottler | None = None,
    extra_query: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch all items in a folder across all pages."""
    all_files: list[dict[str, Any]] = []
    page_token: str | None = None
    query = build_query(folder_id, extra_query)

    while True:
        params: dict[str, Any] = {
            "q": query,
            "fields": _LIST_FIELDS,
            "pageSize": DEFAULT_PAGE_SIZE,
            "orderBy": "name",
            **_SHARED_DRIVE_KWARGS,
        }
        if page_token:
            params["pageToken"] = page_token

        request = service.files().list(**params)
        if throttler is not None:
            response: dict[str, Any] = throttled_execute(request, throttler)
        else:
            response = request.execute()
        all_files.extend(response.get("files", []))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return all_files


def _deduplicate_names(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Append __{id[:8]} suffix to items with duplicate names in the same batch."""
    name_counts: dict[str, int] = {}
    for item in items:
        name = item["name"]
        name_counts[name] = name_counts.get(name, 0) + 1

    result: list[dict[str, Any]] = []
    for item in items:
        if name_counts[item["name"]] > 1:
            item = dict(item)  # copy to avoid mutating original
            item["name"] = f"{item['name']}__{item['id'][:8]}"
        result.append(item)
    return result


def _resolve_shortcut(
    service: Resource,
    shortcut_item: dict[str, Any],
    visited_ids: set[str],
    throttler: TokenBucketThrottler | None = None,
) -> dict[str, Any] | None:
    """Fetch the shortcut's target file metadata. Returns None on cycle."""
    target_id = (shortcut_item.get("shortcutDetails") or {}).get("targetId")
    if (not target_id) or (target_id in visited_ids):
        logger.warning(
            "Skipping shortcut cycle or missing target: %s -> %s",
            shortcut_item.get("id"),
            target_id,
        )
        return None

    visited_ids.add(target_id)
    try:
        request = service.files().get(
            fileId=target_id,
            fields=_GET_FIELDS,
            **_SHARED_DRIVE_KWARGS,
        )
        if throttler is not None:
            result: dict[str, Any] = throttled_execute(request, throttler)
        else:
            result = request.execute()
        return result
    except Exception as exc:
        logger.warning("Could not resolve shortcut target %s: %s", target_id, exc)
        return None


def _build_drive_item(raw: dict[str, Any], local_base: Path) -> DriveItem:
    """Map a Drive API file dict to a DriveItem dataclass."""
    capabilities = raw.get("capabilities") or {}
    size_str = raw.get("size") or raw.get("quotaBytesUsed")
    size = int(size_str) if size_str else None
    drive_path = str(local_base / raw["name"]) if local_base != Path() else raw["name"]

    return DriveItem(
        id=raw["id"],
        name=raw["name"],
        mime_type=raw["mimeType"],
        size=size,
        md5_checksum=raw.get("md5Checksum"),
        created_time=raw.get("createdTime", ""),
        modified_time=raw.get("modifiedTime", ""),
        parents=raw.get("parents", []),
        drive_path=drive_path,
        is_folder=(raw["mimeType"] == FOLDER_MIME),
        can_download=bool(capabilities.get("canDownload", True)),
        is_shortcut=(raw["mimeType"] == SHORTCUT_MIME),
        shortcut_target_id=(raw.get("shortcutDetails") or {}).get("targetId"),
        shared_drive_id=raw.get("driveId"),
    )


# ---------------------------------------------------------------------------
# Shared Drive detection and discovery
# ---------------------------------------------------------------------------


def detect_drive_context(service: Resource, folder_id: str) -> DriveContext:
    """Determine if a folder lives in My Drive or a Shared Drive."""
    meta: dict[str, Any] = (
        service.files()
        .get(fileId=folder_id, fields="id,driveId", supportsAllDrives=True)
        .execute()
    )

    drive_id = meta.get("driveId")
    if drive_id:
        return DriveContext(DriveType.SHARED_DRIVE, drive_id)
    return DriveContext(DriveType.MY_DRIVE, None)


def list_shared_drives(service: Resource) -> list[dict[str, Any]]:
    """List all accessible Shared Drives, handling pagination."""
    drives: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        params: dict[str, Any] = {
            "pageSize": 100,
            "fields": "nextPageToken,drives(id,name,createdTime)",
        }
        if page_token:
            params["pageToken"] = page_token

        result: dict[str, Any] = service.drives().list(**params).execute()
        drives.extend(result.get("drives", []))

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return drives
