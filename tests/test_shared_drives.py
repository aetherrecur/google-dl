"""Tests for Shared Drive support: DriveContext, detection, discovery, selection."""

from __future__ import annotations

from unittest.mock import patch

from gdrive_dl.constants import DriveType
from gdrive_dl.walker import DriveContext, detect_drive_context, list_shared_drives

# ---------------------------------------------------------------------------
# DriveContext
# ---------------------------------------------------------------------------


class TestDriveContext:
    def test_my_drive_list_kwargs(self):
        """my_drive context includes supportsAllDrives but no corpora/driveId."""
        ctx = DriveContext(DriveType.MY_DRIVE, drive_id=None)
        kwargs = ctx.list_kwargs()

        assert kwargs["supportsAllDrives"] is True
        assert kwargs["includeItemsFromAllDrives"] is True
        assert "corpora" not in kwargs
        assert "driveId" not in kwargs

    def test_shared_drive_list_kwargs(self):
        """shared_drive context includes corpora='drive' and driveId."""
        ctx = DriveContext(DriveType.SHARED_DRIVE, drive_id="0AExampleDriveId")
        kwargs = ctx.list_kwargs()

        assert kwargs["supportsAllDrives"] is True
        assert kwargs["includeItemsFromAllDrives"] is True
        assert kwargs["corpora"] == "drive"
        assert kwargs["driveId"] == "0AExampleDriveId"

    def test_get_kwargs(self):
        """get_kwargs returns supportsAllDrives only."""
        ctx = DriveContext(DriveType.MY_DRIVE, drive_id=None)
        kwargs = ctx.get_kwargs()

        assert kwargs == {"supportsAllDrives": True}

    def test_get_kwargs_shared_drive(self):
        """get_kwargs is the same for shared drives (no driveId needed)."""
        ctx = DriveContext(DriveType.SHARED_DRIVE, drive_id="0AExampleDriveId")
        kwargs = ctx.get_kwargs()

        assert kwargs == {"supportsAllDrives": True}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class TestDetectDriveContext:
    def test_detect_my_drive(self, mock_service):
        """Folder without driveId returns MY_DRIVE context."""
        mock_service.files.return_value.get.return_value.execute.return_value = {
            "id": "folder123",
        }

        ctx = detect_drive_context(mock_service, "folder123")

        assert ctx.drive_type == DriveType.MY_DRIVE
        assert ctx.drive_id is None

    def test_detect_shared_drive(self, mock_service):
        """Folder with driveId returns SHARED_DRIVE context with drive ID."""
        mock_service.files.return_value.get.return_value.execute.return_value = {
            "id": "folder456",
            "driveId": "0ASharedDrive123",
        }

        ctx = detect_drive_context(mock_service, "folder456")

        assert ctx.drive_type == DriveType.SHARED_DRIVE
        assert ctx.drive_id == "0ASharedDrive123"

    def test_detect_passes_supports_all_drives(self, mock_service):
        """detect_drive_context passes supportsAllDrives=True to API call."""
        mock_service.files.return_value.get.return_value.execute.return_value = {
            "id": "folder789",
        }

        detect_drive_context(mock_service, "folder789")

        call_kwargs = mock_service.files.return_value.get.call_args
        assert call_kwargs.kwargs.get("supportsAllDrives") is True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestListSharedDrives:
    def test_single_page(self, mock_service):
        """Returns drives from a single page."""
        mock_service.drives.return_value.list.return_value.execute.return_value = {
            "drives": [
                {"id": "d1", "name": "Engineering"},
                {"id": "d2", "name": "Marketing"},
            ],
        }

        result = list_shared_drives(mock_service)

        assert len(result) == 2
        assert result[0]["name"] == "Engineering"
        assert result[1]["name"] == "Marketing"

    def test_pagination(self, mock_service):
        """Handles multiple pages via nextPageToken."""
        mock_service.drives.return_value.list.return_value.execute.side_effect = [
            {
                "drives": [{"id": "d1", "name": "Drive A"}],
                "nextPageToken": "token2",
            },
            {
                "drives": [{"id": "d2", "name": "Drive B"}],
            },
        ]

        result = list_shared_drives(mock_service)

        assert len(result) == 2
        assert result[0]["name"] == "Drive A"
        assert result[1]["name"] == "Drive B"

    def test_empty(self, mock_service):
        """Returns empty list when no drives accessible."""
        mock_service.drives.return_value.list.return_value.execute.return_value = {
            "drives": [],
        }

        result = list_shared_drives(mock_service)

        assert result == []


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


class TestSelectSharedDrives:
    def test_select_all(self, mock_service):
        """'all' input selects all drives."""
        from gdrive_dl.cli import select_shared_drives

        mock_service.drives.return_value.list.return_value.execute.return_value = {
            "drives": [
                {"id": "d1", "name": "Drive A"},
                {"id": "d2", "name": "Drive B"},
            ],
        }

        with patch("click.prompt", return_value="all"):
            selected = select_shared_drives(mock_service)

        assert len(selected) == 2

    def test_select_specific(self, mock_service):
        """Comma-separated numbers select specific drives."""
        from gdrive_dl.cli import select_shared_drives

        mock_service.drives.return_value.list.return_value.execute.return_value = {
            "drives": [
                {"id": "d1", "name": "Drive A"},
                {"id": "d2", "name": "Drive B"},
                {"id": "d3", "name": "Drive C"},
            ],
        }

        with patch("click.prompt", return_value="1,3"):
            selected = select_shared_drives(mock_service)

        assert len(selected) == 2
        assert selected[0]["name"] == "Drive A"
        assert selected[1]["name"] == "Drive C"

    def test_none_available(self, mock_service):
        """Shows message and returns empty list when no drives exist."""
        from gdrive_dl.cli import select_shared_drives

        mock_service.drives.return_value.list.return_value.execute.return_value = {
            "drives": [],
        }

        selected = select_shared_drives(mock_service)

        assert selected == []


# ---------------------------------------------------------------------------
# supportsAllDrives on download API calls
# ---------------------------------------------------------------------------


class TestSupportsAllDrives:
    def test_download_blob_includes_supports_all_drives(self, mock_service):
        """get_media call includes supportsAllDrives=True."""
        from gdrive_dl.downloader import _download_blob
        from gdrive_dl.walker import DriveItem

        item = DriveItem(
            id="file1", name="test.pdf", mime_type="application/pdf",
            size=100, md5_checksum="abc", created_time="", modified_time="",
            parents=[], drive_path="test.pdf", is_folder=False,
            can_download=True, is_shortcut=False, shortcut_target_id=None,
            shared_drive_id=None,
        )

        # Make get_media raise to short-circuit download
        mock_service.files.return_value.get_media.side_effect = Exception("test stop")

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            _download_blob(mock_service, item, Path(td) / "test.pdf")

        call_kwargs = mock_service.files.return_value.get_media.call_args
        assert call_kwargs.kwargs.get("supportsAllDrives") is True
