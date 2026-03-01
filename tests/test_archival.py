"""Tests for gdrive_dl.archival — permissions, comments, metadata, revisions."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from gdrive_dl.archival import (
    save_comments,
    save_metadata,
    save_permissions,
    save_revisions,
)
from gdrive_dl.constants import FOLDER_MIME
from gdrive_dl.throttle import TokenBucketThrottler
from gdrive_dl.walker import DriveItem


def _item(
    file_id: str = "f1",
    name: str = "report.pdf",
    mime_type: str = "application/pdf",
    size: int | None = 1024,
    is_folder: bool = False,
    drive_path: str | None = None,
) -> DriveItem:
    return DriveItem(
        id=file_id,
        name=name,
        mime_type=mime_type,
        size=size,
        md5_checksum="abc123",
        created_time="2025-01-01T00:00:00.000Z",
        modified_time="2025-06-01T00:00:00.000Z",
        parents=["root"],
        drive_path=drive_path or name,
        is_folder=is_folder,
        can_download=True,
        is_shortcut=False,
        shortcut_target_id=None,
        shared_drive_id=None,
        export_links=None,
    )


def _throttler() -> TokenBucketThrottler:
    return TokenBucketThrottler(rate=100.0)


# ---------------------------------------------------------------------------
# save_permissions
# ---------------------------------------------------------------------------


class TestSavePermissions:
    """Permissions sidecar creation."""

    def test_creates_sidecar_for_file(self, tmp_path):
        service = MagicMock()
        service.permissions.return_value.list.return_value.execute.return_value = {
            "permissions": [
                {
                    "id": "p1",
                    "type": "user",
                    "role": "writer",
                    "emailAddress": "alice@example.com",
                    "displayName": "Alice",
                },
            ],
        }
        item = _item(drive_path="docs/report.pdf")
        dest = tmp_path / "docs"
        dest.mkdir(parents=True)

        save_permissions(service, item, tmp_path, _throttler())

        sidecar = dest / "report.pdf.permissions.json"
        assert sidecar.exists()
        data = json.loads(sidecar.read_text())
        assert data["fileId"] == "f1"
        assert data["fileName"] == "report.pdf"
        assert len(data["permissions"]) == 1
        assert "capturedAt" in data

    def test_folder_sidecar_naming(self, tmp_path):
        service = MagicMock()
        service.permissions.return_value.list.return_value.execute.return_value = {
            "permissions": [],
        }
        item = _item(
            file_id="d1", name="docs", mime_type=FOLDER_MIME,
            is_folder=True, drive_path="docs",
        )
        (tmp_path / "docs").mkdir()

        save_permissions(service, item, tmp_path, _throttler())

        sidecar = tmp_path / "docs" / ".folder.permissions.json"
        assert sidecar.exists()

    def test_summary_counts(self, tmp_path):
        service = MagicMock()
        service.permissions.return_value.list.return_value.execute.return_value = {
            "permissions": [
                {
                    "id": "p1", "type": "user", "role": "writer",
                    "permissionDetails": [
                        {"inherited": False},
                    ],
                },
                {
                    "id": "p2", "type": "user", "role": "reader",
                    "permissionDetails": [
                        {"inherited": True, "inheritedFrom": "parent1"},
                    ],
                },
            ],
        }
        item = _item(drive_path="report.pdf")
        save_permissions(service, item, tmp_path, _throttler())

        data = json.loads((tmp_path / "report.pdf.permissions.json").read_text())
        assert data["summary"]["directPermissions"] == 1
        assert data["summary"]["inheritedPermissions"] == 1

    def test_api_error_does_not_raise(self, tmp_path):
        service = MagicMock()
        service.permissions.return_value.list.return_value.execute.side_effect = (
            Exception("API error")
        )
        item = _item()
        # Should not raise
        save_permissions(service, item, tmp_path, _throttler())


# ---------------------------------------------------------------------------
# save_comments
# ---------------------------------------------------------------------------


class TestSaveComments:
    """Comments sidecar creation."""

    def test_creates_sidecar(self, tmp_path):
        service = MagicMock()
        service.comments.return_value.list.return_value.execute.return_value = {
            "comments": [
                {
                    "id": "c1",
                    "author": {"displayName": "Alice", "emailAddress": "alice@example.com"},
                    "content": "Nice report!",
                    "createdTime": "2025-05-01T10:00:00Z",
                    "modifiedTime": "2025-05-01T10:00:00Z",
                    "resolved": False,
                    "replies": [],
                },
            ],
        }
        item = _item(drive_path="report.pdf")
        save_comments(service, item, tmp_path, _throttler())

        sidecar = tmp_path / "report.pdf.comments.json"
        assert sidecar.exists()
        data = json.loads(sidecar.read_text())
        assert data["fileId"] == "f1"
        assert len(data["comments"]) == 1
        assert data["comments"][0]["content"] == "Nice report!"

    def test_includes_replies(self, tmp_path):
        service = MagicMock()
        service.comments.return_value.list.return_value.execute.return_value = {
            "comments": [
                {
                    "id": "c1",
                    "author": {"displayName": "Alice"},
                    "content": "Question?",
                    "replies": [
                        {
                            "author": {"displayName": "Bob"},
                            "content": "Answer!",
                            "createdTime": "2025-05-02T10:00:00Z",
                        },
                    ],
                },
            ],
        }
        item = _item(drive_path="report.pdf")
        save_comments(service, item, tmp_path, _throttler())

        data = json.loads((tmp_path / "report.pdf.comments.json").read_text())
        assert len(data["comments"][0]["replies"]) == 1

    def test_api_error_does_not_raise(self, tmp_path):
        service = MagicMock()
        service.comments.return_value.list.return_value.execute.side_effect = (
            Exception("API error")
        )
        item = _item()
        save_comments(service, item, tmp_path, _throttler())


# ---------------------------------------------------------------------------
# save_metadata
# ---------------------------------------------------------------------------


class TestSaveMetadata:
    """Metadata sidecar creation (local only, no API)."""

    def test_creates_sidecar(self, tmp_path):
        item = _item(drive_path="report.pdf")
        save_metadata(item, tmp_path)

        sidecar = tmp_path / "report.pdf.metadata.json"
        assert sidecar.exists()
        data = json.loads(sidecar.read_text())
        assert data["id"] == "f1"
        assert data["name"] == "report.pdf"
        assert data["mimeType"] == "application/pdf"
        assert data["size"] == 1024
        assert data["modifiedTime"] == "2025-06-01T00:00:00.000Z"

    def test_no_api_call(self, tmp_path):
        """save_metadata does not take a service parameter."""
        item = _item(drive_path="report.pdf")
        # Just verify it works without service — signature doesn't include it
        save_metadata(item, tmp_path)
        assert (tmp_path / "report.pdf.metadata.json").exists()

    def test_folder_sidecar_naming(self, tmp_path):
        item = _item(
            file_id="d1", name="docs", mime_type=FOLDER_MIME,
            is_folder=True, drive_path="docs",
        )
        (tmp_path / "docs").mkdir()
        save_metadata(item, tmp_path)

        sidecar = tmp_path / "docs" / ".folder.metadata.json"
        assert sidecar.exists()


# ---------------------------------------------------------------------------
# save_revisions
# ---------------------------------------------------------------------------


class TestSaveRevisions:
    """Revision history listing and download."""

    def test_creates_revisions_dir_and_metadata(self, tmp_path):
        service = MagicMock()
        service.revisions.return_value.list.return_value.execute.return_value = {
            "revisions": [
                {
                    "id": "rev1",
                    "modifiedTime": "2025-03-01T10:00:00Z",
                    "mimeType": "application/pdf",
                    "keepForever": False,
                    "size": "500",
                },
                {
                    "id": "rev2",
                    "modifiedTime": "2025-06-01T10:00:00Z",
                    "mimeType": "application/pdf",
                    "keepForever": False,
                    "size": "1024",
                },
            ],
        }
        item = _item(drive_path="report.pdf")
        save_revisions(service, item, tmp_path, _throttler(), creds=None)

        rev_dir = tmp_path / "report.pdf.revisions"
        assert rev_dir.is_dir()
        meta = json.loads((rev_dir / "revisions.json").read_text())
        assert len(meta["revisions"]) == 2

    def test_last_n_revisions(self, tmp_path):
        service = MagicMock()
        service.revisions.return_value.list.return_value.execute.return_value = {
            "revisions": [
                {"id": "rev1", "modifiedTime": "2025-01-01T10:00:00Z"},
                {"id": "rev2", "modifiedTime": "2025-03-01T10:00:00Z"},
                {"id": "rev3", "modifiedTime": "2025-06-01T10:00:00Z"},
            ],
        }
        item = _item(drive_path="report.pdf")
        save_revisions(service, item, tmp_path, _throttler(), creds=None, revision_count=2)

        meta = json.loads(
            (tmp_path / "report.pdf.revisions" / "revisions.json").read_text()
        )
        assert len(meta["revisions"]) == 2
        assert meta["revisions"][0]["id"] == "rev2"

    @patch("gdrive_dl.archival.MediaIoBaseDownload")
    def test_downloads_blob_revision_with_keep_forever(self, mock_media, tmp_path):
        service = MagicMock()
        service.revisions.return_value.list.return_value.execute.return_value = {
            "revisions": [
                {
                    "id": "rev1",
                    "modifiedTime": "2025-06-01T10:00:00Z",
                    "mimeType": "application/pdf",
                    "keepForever": True,
                    "originalFilename": "report.pdf",
                },
            ],
        }
        mock_dl = MagicMock()
        mock_media.return_value = mock_dl
        mock_dl.next_chunk.return_value = (MagicMock(resumable_progress=500), True)

        item = _item(drive_path="report.pdf")
        save_revisions(service, item, tmp_path, _throttler(), creds=None)

        # Should have attempted to download via get_media
        service.revisions.return_value.get_media.assert_called_once()

    def test_api_error_does_not_raise(self, tmp_path):
        service = MagicMock()
        service.revisions.return_value.list.return_value.execute.side_effect = (
            Exception("API error")
        )
        item = _item()
        save_revisions(service, item, tmp_path, _throttler(), creds=None)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestArchivalErrorHandling:
    """All archival functions are best-effort."""

    def test_permissions_failure_non_fatal(self, tmp_path):
        service = MagicMock()
        service.permissions.return_value.list.return_value.execute.side_effect = (
            RuntimeError("network")
        )
        save_permissions(service, _item(), tmp_path, _throttler())
        # No exception raised

    def test_comments_failure_non_fatal(self, tmp_path):
        service = MagicMock()
        service.comments.return_value.list.return_value.execute.side_effect = (
            RuntimeError("network")
        )
        save_comments(service, _item(), tmp_path, _throttler())

    def test_revisions_failure_non_fatal(self, tmp_path):
        service = MagicMock()
        service.revisions.return_value.list.return_value.execute.side_effect = (
            RuntimeError("network")
        )
        save_revisions(service, _item(), tmp_path, _throttler(), creds=None)
