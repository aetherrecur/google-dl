"""Download orchestration: blob files via MediaIoBaseDownload, Workspace via export."""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from gdrive_dl.constants import EXPORT_FORMATS, NON_DOWNLOADABLE
from gdrive_dl.manifest import DownloadStatus
from gdrive_dl.walker import DriveItem

logger = logging.getLogger(__name__)

_1MB = 1 * 1024 * 1024
_5MB = 5 * 1024 * 1024
_10MB = 10 * 1024 * 1024
_100MB = 100 * 1024 * 1024


@dataclass
class DownloadResult:
    """Outcome of a single file download attempt."""

    file_id: str
    name: str
    status: DownloadStatus
    local_path: Path | None = None
    bytes_downloaded: int = 0
    error_message: str | None = None
    export_format: str | None = None


def download_file(
    service: Resource,
    item: DriveItem,
    local_path: Path,
    creds: Any | None = None,
    export_links: dict[str, str] | None = None,
) -> DownloadResult:
    """Route a DriveItem to the appropriate download strategy.

    Returns a DownloadResult. Never raises — all errors are captured in result.
    """
    if item.mime_type in NON_DOWNLOADABLE:
        logger.info("Skipping non-downloadable: %s (%s)", item.name, item.mime_type)
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.SKIPPED,
            error_message=f"Non-downloadable type: {item.mime_type}",
        )

    if item.is_workspace_file:
        return _export_workspace(
            service, item, local_path, creds=creds, export_links=export_links,
        )

    return _download_blob(service, item, local_path)


def _download_blob(
    service: Resource,
    item: DriveItem,
    dest_path: Path,
) -> DownloadResult:
    """Stream a blob file to disk using MediaIoBaseDownload."""
    chunk_size = _select_chunk_size(item.size)
    partial_path = dest_path.with_suffix(dest_path.suffix + ".partial")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        request = service.files().get_media(fileId=item.id)
        fh = io.FileIO(str(partial_path), "wb")
        downloader = MediaIoBaseDownload(fh, request, chunksize=chunk_size)

        done = False
        bytes_downloaded = 0
        while not done:
            status, done = downloader.next_chunk()
            if status:
                bytes_downloaded = status.resumable_progress

        fh.close()
        os.replace(partial_path, dest_path)

        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.COMPLETED,
            local_path=dest_path,
            bytes_downloaded=bytes_downloaded,
        )
    except Exception as exc:
        logger.warning("Blob download failed for %s: %s", item.name, exc)
        # Clean up partial file
        try:
            if partial_path.exists():
                partial_path.unlink()
        except OSError:
            pass
        try:
            fh.close()
        except Exception:
            pass
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.FAILED,
            error_message=str(exc),
        )


def _export_workspace(
    service: Resource,
    item: DriveItem,
    dest_path: Path,
    creds: Any | None = None,
    export_links: dict[str, str] | None = None,
) -> DownloadResult:
    """Export a Workspace file (Docs, Sheets, Slides, etc.)."""
    format_entry = EXPORT_FORMATS.get(item.mime_type)
    if format_entry is None:
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.FAILED,
            error_message=f"No export format for MIME type: {item.mime_type}",
        )

    export_mime, _ext = format_entry
    partial_path = dest_path.with_suffix(dest_path.suffix + ".partial")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        request = service.files().export_media(
            fileId=item.id, mimeType=export_mime,
        )
        fh = io.FileIO(str(partial_path), "wb")
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        bytes_downloaded = 0
        while not done:
            status, done = downloader.next_chunk()
            if status:
                bytes_downloaded = status.resumable_progress

        fh.close()
        os.replace(partial_path, dest_path)

        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.COMPLETED,
            local_path=dest_path,
            bytes_downloaded=bytes_downloaded,
            export_format=export_mime,
        )
    except HttpError as exc:
        # Check for exportSizeLimitExceeded → fallback to exportLinks
        if exc.resp.status == 403 and _is_export_size_limit(exc):
            try:
                fh.close()
            except Exception:
                pass
            try:
                if partial_path.exists():
                    partial_path.unlink()
            except OSError:
                pass
            return _export_via_links(
                item, dest_path, export_mime, creds, export_links,
            )
        logger.warning("Workspace export failed for %s: %s", item.name, exc)
        _cleanup_partial(partial_path)
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.FAILED,
            error_message=str(exc),
        )
    except Exception as exc:
        logger.warning("Workspace export failed for %s: %s", item.name, exc)
        _cleanup_partial(partial_path)
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.FAILED,
            error_message=str(exc),
        )


def _export_via_links(
    item: DriveItem,
    dest_path: Path,
    export_mime: str,
    creds: Any | None,
    export_links: dict[str, str] | None,
) -> DownloadResult:
    """Download large Workspace file via exportLinks URL with Bearer auth."""
    if (not export_links) or (export_mime not in export_links):
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.FAILED,
            error_message="exportSizeLimitExceeded and no exportLinks available",
        )

    if not creds or not hasattr(creds, "token"):
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.FAILED,
            error_message="exportSizeLimitExceeded but no credentials for exportLinks",
        )

    url = export_links[export_mime]
    partial_path = dest_path.with_suffix(dest_path.suffix + ".partial")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        headers = {"Authorization": f"Bearer {creds.token}"}
        with requests.get(url, headers=headers, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            bytes_downloaded = 0
            with open(partial_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=_5MB):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)

        os.replace(partial_path, dest_path)
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.COMPLETED,
            local_path=dest_path,
            bytes_downloaded=bytes_downloaded,
            export_format=export_mime,
        )
    except Exception as exc:
        logger.warning("exportLinks download failed for %s: %s", item.name, exc)
        _cleanup_partial(partial_path)
        return DownloadResult(
            file_id=item.id,
            name=item.name,
            status=DownloadStatus.FAILED,
            error_message=str(exc),
        )


def _select_chunk_size(file_size: int | None) -> int:
    """Select download chunk size based on file size."""
    if file_size is None:
        return _5MB
    if file_size < _1MB:
        return -1  # whole file in single request
    if file_size < _100MB:
        return _5MB
    return _10MB


def _is_export_size_limit(exc: HttpError) -> bool:
    """Check if an HttpError is due to exportSizeLimitExceeded."""
    try:
        import json
        body = json.loads(exc.content.decode("utf-8"))
        errors = body.get("error", {}).get("errors", [])
        return any(e.get("reason") == "exportSizeLimitExceeded" for e in errors)
    except Exception:
        return False


def _cleanup_partial(partial_path: Path) -> None:
    """Remove partial file if it exists."""
    try:
        if partial_path.exists():
            partial_path.unlink()
    except OSError:
        pass
