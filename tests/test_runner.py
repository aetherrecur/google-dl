"""Tests for gdrive_dl.runner — DownloadRunner orchestration."""

from unittest.mock import MagicMock, patch

from gdrive_dl.downloader import DownloadResult
from gdrive_dl.manifest import DownloadStatus, Manifest
from gdrive_dl.runner import DownloadRunner, SessionResult
from gdrive_dl.walker import DriveItem


def _make_item(
    file_id: str = "f1",
    name: str = "test.pdf",
    mime_type: str = "application/pdf",
    is_folder: bool = False,
    size: int = 1024,
    **kwargs,
) -> DriveItem:
    defaults = {
        "id": file_id,
        "name": name,
        "mime_type": mime_type,
        "size": size,
        "md5_checksum": "abc123",
        "created_time": "2024-01-01T00:00:00.000Z",
        "modified_time": "2024-06-01T00:00:00.000Z",
        "parents": ["root"],
        "drive_path": name,
        "is_folder": is_folder,
        "can_download": True,
        "is_shortcut": False,
        "shortcut_target_id": None,
        "shared_drive_id": None,
        "export_links": None,
    }
    defaults.update(kwargs)
    return DriveItem(**defaults)


# ---------------------------------------------------------------------------
# SessionResult
# ---------------------------------------------------------------------------


class TestSessionResult:
    """SessionResult tracks aggregate download outcomes."""

    def test_default_values(self):
        r = SessionResult()
        assert r.files_completed == 0
        assert r.files_failed == 0
        assert r.files_skipped == 0
        assert r.bytes_downloaded == 0


# ---------------------------------------------------------------------------
# DownloadRunner
# ---------------------------------------------------------------------------


class TestDownloadRunner:
    """DownloadRunner coordinates walk → download → checksum → timestamp → manifest."""

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    @patch("gdrive_dl.runner.checksums")
    @patch("gdrive_dl.runner.timestamps")
    def test_full_flow_downloads_files(
        self, mock_ts, mock_cs, mock_dl, mock_walker, tmp_path
    ):
        """Runner walks, downloads, verifies checksums, applies timestamps."""
        items = [_make_item(file_id="f1", name="doc.pdf")]
        mock_walker.walk.return_value = items
        mock_dl.download_file.return_value = DownloadResult(
            file_id="f1", name="doc.pdf", status=DownloadStatus.COMPLETED,
            local_path=tmp_path / "doc.pdf", bytes_downloaded=1024,
        )
        mock_cs.verify_checksum.return_value = True

        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        service = MagicMock()

        runner = DownloadRunner(
            service=service,
            output_dir=tmp_path,
            manifest=manifest,
            creds=None,
        )
        result = runner.run("root_folder")

        assert result.files_completed == 1
        assert result.bytes_downloaded == 1024
        mock_dl.download_file.assert_called_once()
        mock_cs.verify_checksum.assert_called_once()
        mock_ts.apply_timestamps.assert_called_once()

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    def test_skips_completed_files(self, mock_dl, mock_walker, tmp_path):
        """Files already completed in manifest with same modifiedTime are skipped."""
        items = [_make_item(
            file_id="f1", name="doc.pdf",
            modified_time="2024-06-01T00:00:00.000Z",
        )]
        mock_walker.walk.return_value = items

        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        manifest.update_file(
            "f1", DownloadStatus.COMPLETED,
            modifiedTime="2024-06-01T00:00:00.000Z",
        )

        service = MagicMock()
        runner = DownloadRunner(
            service=service, output_dir=tmp_path, manifest=manifest, creds=None,
        )
        result = runner.run("root_folder")

        mock_dl.download_file.assert_not_called()
        assert result.files_completed == 0  # was already done, not counted this session

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    def test_creates_directories_for_folders(self, mock_dl, mock_walker, tmp_path):
        """Folder items are created as local directories."""
        items = [
            _make_item(
                file_id="dir1", name="SubDir",
                mime_type="application/vnd.google-apps.folder",
                is_folder=True, size=0, md5_checksum=None,
            ),
        ]
        mock_walker.walk.return_value = items

        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        service = MagicMock()
        runner = DownloadRunner(
            service=service, output_dir=tmp_path, manifest=manifest, creds=None,
        )
        runner.run("root_folder")

        assert (tmp_path / "SubDir").is_dir()
        mock_dl.download_file.assert_not_called()

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    def test_failed_download_tracked(self, mock_dl, mock_walker, tmp_path):
        """Failed downloads are counted and recorded in manifest."""
        items = [_make_item(file_id="f1", name="bad.pdf")]
        mock_walker.walk.return_value = items
        mock_dl.download_file.return_value = DownloadResult(
            file_id="f1", name="bad.pdf", status=DownloadStatus.FAILED,
            error_message="Network error",
        )

        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        service = MagicMock()
        runner = DownloadRunner(
            service=service, output_dir=tmp_path, manifest=manifest, creds=None,
        )
        result = runner.run("root_folder")

        assert result.files_failed == 1
        assert manifest._data["files"]["f1"]["status"] == "failed"

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    def test_manifest_saved_on_completion(self, mock_dl, mock_walker, tmp_path):
        """Manifest is saved to disk after run completes."""
        mock_walker.walk.return_value = []
        manifest_path = tmp_path / "manifest.json"
        manifest = Manifest.load_or_create(str(manifest_path))
        # Make manifest dirty so save actually writes
        manifest.update_file("setup", DownloadStatus.PENDING)

        service = MagicMock()
        runner = DownloadRunner(
            service=service, output_dir=tmp_path, manifest=manifest, creds=None,
        )
        runner.run("root_folder")

        assert manifest_path.exists()

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    def test_skip_completed_unchanged(self, mock_dl, mock_walker, tmp_path):
        """Completed file with same modifiedTime is skipped."""
        items = [_make_item(
            file_id="f1", name="doc.pdf",
            modified_time="2024-06-01T00:00:00.000Z",
        )]
        mock_walker.walk.return_value = items

        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        manifest.update_file(
            "f1", DownloadStatus.COMPLETED,
            modifiedTime="2024-06-01T00:00:00.000Z",
        )

        service = MagicMock()
        runner = DownloadRunner(
            service=service, output_dir=tmp_path, manifest=manifest, creds=None,
        )
        result = runner.run("root_folder")

        mock_dl.download_file.assert_not_called()
        assert result.files_completed == 0

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    @patch("gdrive_dl.runner.checksums")
    @patch("gdrive_dl.runner.timestamps")
    def test_redownload_completed_changed(
        self, mock_ts, mock_cs, mock_dl, mock_walker, tmp_path,
    ):
        """Completed file with different modifiedTime is re-downloaded."""
        items = [_make_item(
            file_id="f1", name="doc.pdf",
            modified_time="2024-07-01T00:00:00.000Z",
        )]
        mock_walker.walk.return_value = items
        mock_dl.download_file.return_value = DownloadResult(
            file_id="f1", name="doc.pdf", status=DownloadStatus.COMPLETED,
            local_path=tmp_path / "doc.pdf", bytes_downloaded=2048,
        )
        mock_cs.verify_checksum.return_value = True

        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        manifest.update_file(
            "f1", DownloadStatus.COMPLETED,
            modifiedTime="2024-06-01T00:00:00.000Z",
        )

        service = MagicMock()
        runner = DownloadRunner(
            service=service, output_dir=tmp_path, manifest=manifest, creds=None,
        )
        result = runner.run("root_folder")

        mock_dl.download_file.assert_called_once()
        assert result.files_completed == 1

    @patch("gdrive_dl.runner.walker")
    @patch("gdrive_dl.runner.downloader")
    @patch("gdrive_dl.runner.timestamps")
    def test_no_verify_skips_checksum(
        self, mock_ts, mock_dl, mock_walker, tmp_path,
    ):
        """no_verify=True bypasses checksum verification."""
        items = [_make_item(file_id="f1", name="doc.pdf")]
        mock_walker.walk.return_value = items
        mock_dl.download_file.return_value = DownloadResult(
            file_id="f1", name="doc.pdf", status=DownloadStatus.COMPLETED,
            local_path=tmp_path / "doc.pdf", bytes_downloaded=1024,
        )

        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        service = MagicMock()
        runner = DownloadRunner(
            service=service, output_dir=tmp_path, manifest=manifest,
            creds=None, no_verify=True,
        )

        with patch("gdrive_dl.runner.checksums") as mock_cs:
            result = runner.run("root_folder")
            mock_cs.verify_checksum.assert_not_called()

        assert result.files_completed == 1
