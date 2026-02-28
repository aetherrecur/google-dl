"""Shared test fixtures for gdrive_dl tests."""

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_output_dir(tmp_path):
    """Temporary directory for download output."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def mock_service():
    """A MagicMock Drive API v3 Resource with default empty responses."""
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [],
    }
    return service


def make_file_item(
    file_id: str = "file1",
    name: str = "test.pdf",
    mime_type: str = "application/pdf",
    size: Optional[str] = "1024",
    md5: Optional[str] = "abc123",
    created: str = "2024-01-01T00:00:00.000Z",
    modified: str = "2024-06-01T00:00:00.000Z",
    parents: Optional[list[str]] = None,
    can_download: bool = True,
    drive_id: Optional[str] = None,
    export_links: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Factory for a Drive API file response dict."""
    item: dict[str, Any] = {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "createdTime": created,
        "modifiedTime": modified,
        "parents": parents or ["root"],
        "capabilities": {"canDownload": can_download},
    }
    if size is not None:
        item["size"] = size
    if md5 is not None:
        item["md5Checksum"] = md5
    if drive_id is not None:
        item["driveId"] = drive_id
    if export_links is not None:
        item["exportLinks"] = export_links
    return item


def make_folder_item(
    file_id: str = "folder1",
    name: str = "Documents",
    parents: Optional[list[str]] = None,
    drive_id: Optional[str] = None,
) -> dict[str, Any]:
    """Factory for a Drive API folder response dict."""
    return make_file_item(
        file_id=file_id,
        name=name,
        mime_type="application/vnd.google-apps.folder",
        size=None,
        md5=None,
        parents=parents,
        drive_id=drive_id,
    )


def make_shortcut_item(
    file_id: str = "shortcut1",
    name: str = "My Shortcut",
    target_id: str = "target1",
    target_mime: str = "application/pdf",
    parents: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Factory for a Drive API shortcut response dict."""
    item = make_file_item(
        file_id=file_id,
        name=name,
        mime_type="application/vnd.google-apps.shortcut",
        size=None,
        md5=None,
        parents=parents,
    )
    item["shortcutDetails"] = {
        "targetId": target_id,
        "targetMimeType": target_mime,
    }
    return item
