"""Tests for gdrive_dl.downloader — blob download, workspace export, routing."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from gdrive_dl.constants import EXPORT_FORMATS, FOLDER_MIME
from gdrive_dl.downloader import (
    DownloadResult,
    _select_chunk_size,
    download_file,
)
from gdrive_dl.manifest import DownloadStatus
from gdrive_dl.walker import DriveItem


def _make_item(
    file_id: str = "f1",
    name: str = "test.pdf",
    mime_type: str = "application/pdf",
    size: int = 1024,
    md5: str = "abc123",
    **kwargs,
) -> DriveItem:
    """Helper to create DriveItem for downloader tests."""
    defaults = {
        "id": file_id,
        "name": name,
        "mime_type": mime_type,
        "size": size,
        "md5_checksum": md5,
        "created_time": "2024-01-01T00:00:00.000Z",
        "modified_time": "2024-06-01T00:00:00.000Z",
        "parents": ["root"],
        "drive_path": name,
        "is_folder": False,
        "can_download": True,
        "is_shortcut": False,
        "shortcut_target_id": None,
        "shared_drive_id": None,
        "export_links": None,
    }
    defaults.update(kwargs)
    return DriveItem(**defaults)


# ---------------------------------------------------------------------------
# Chunk size selection
# ---------------------------------------------------------------------------


class TestSelectChunkSize:
    """Chunk size varies by file size."""

    def test_small_file_single_chunk(self):
        """Files < 1 MB use -1 (whole file)."""
        assert _select_chunk_size(500_000) == -1

    def test_medium_file_5mb_chunks(self):
        """Files 1-100 MB use 5 MB chunks."""
        assert _select_chunk_size(50_000_000) == 5 * 1024 * 1024

    def test_large_file_10mb_chunks(self):
        """Files > 100 MB use 10 MB chunks."""
        assert _select_chunk_size(200_000_000) == 10 * 1024 * 1024

    def test_none_size_uses_default(self):
        """When size is None (workspace), default to 5 MB."""
        assert _select_chunk_size(None) == 5 * 1024 * 1024

    def test_zero_size(self):
        """Zero-byte file uses single chunk."""
        assert _select_chunk_size(0) == -1


# ---------------------------------------------------------------------------
# download_file routing
# ---------------------------------------------------------------------------


class TestDownloadFileRouting:
    """download_file routes to correct strategy based on MIME type."""

    def test_non_downloadable_returns_skipped(self):
        """Files in NON_DOWNLOADABLE are skipped."""
        for mime in ["application/vnd.google-apps.form", "application/vnd.google-apps.site"]:
            item = _make_item(mime_type=mime, size=0, md5=None,
                              is_folder=(mime == FOLDER_MIME))
            result = download_file(MagicMock(), item, Path("/out/test"))

            assert result.status == DownloadStatus.SKIPPED

    @patch("gdrive_dl.downloader._download_blob")
    def test_blob_file_routes_to_download_blob(self, mock_blob):
        """Regular files route to _download_blob."""
        mock_blob.return_value = DownloadResult(
            file_id="f1", name="test.pdf", status=DownloadStatus.COMPLETED,
        )
        item = _make_item()
        result = download_file(MagicMock(), item, Path("/out/test.pdf"))

        mock_blob.assert_called_once()
        assert result.status == DownloadStatus.COMPLETED

    @patch("gdrive_dl.downloader._export_workspace")
    def test_workspace_file_routes_to_export(self, mock_export):
        """Workspace files route to _export_workspace."""
        mock_export.return_value = DownloadResult(
            file_id="d1", name="Doc.docx", status=DownloadStatus.COMPLETED,
        )
        item = _make_item(
            file_id="d1", name="Doc",
            mime_type="application/vnd.google-apps.document",
            size=None, md5=None,
        )
        result = download_file(MagicMock(), item, Path("/out/Doc.docx"))

        mock_export.assert_called_once()
        assert result.status == DownloadStatus.COMPLETED


# ---------------------------------------------------------------------------
# Blob download
# ---------------------------------------------------------------------------


class TestDownloadBlob:
    """_download_blob streams via MediaIoBaseDownload."""

    @patch("gdrive_dl.downloader.MediaIoBaseDownload")
    def test_writes_to_partial_then_renames(self, mock_media_cls, tmp_path):
        """Download writes .partial, renames on success."""
        from gdrive_dl.downloader import _download_blob

        dest = tmp_path / "test.pdf"
        mock_service = MagicMock()
        mock_downloader = MagicMock()
        mock_media_cls.return_value = mock_downloader
        # Simulate single-chunk download
        mock_status = MagicMock()
        mock_status.resumable_progress = 1024
        mock_downloader.next_chunk.return_value = (mock_status, True)

        item = _make_item(size=1024)
        result = _download_blob(mock_service, item, dest)

        assert result.status == DownloadStatus.COMPLETED
        assert dest.exists() or result.local_path == dest  # renamed from .partial

    @patch("gdrive_dl.downloader.MediaIoBaseDownload")
    def test_partial_cleaned_on_failure(self, mock_media_cls, tmp_path):
        """Failed download cleans up .partial file."""
        from gdrive_dl.downloader import _download_blob

        dest = tmp_path / "test.pdf"
        mock_service = MagicMock()
        mock_media_cls.return_value.next_chunk.side_effect = Exception("Network error")

        item = _make_item(size=1024)
        result = _download_blob(mock_service, item, dest)

        assert result.status == DownloadStatus.FAILED
        partial = dest.with_suffix(dest.suffix + ".partial")
        assert not partial.exists()


# ---------------------------------------------------------------------------
# Workspace export
# ---------------------------------------------------------------------------


class TestExportWorkspace:
    """_export_workspace exports Google Docs/Sheets/Slides."""

    @patch("gdrive_dl.downloader.MediaIoBaseDownload")
    def test_exports_doc_to_docx(self, mock_media_cls, tmp_path):
        """Google Doc exports to .docx with correct MIME type."""
        from gdrive_dl.downloader import _export_workspace

        dest = tmp_path / "Doc.docx"
        mock_service = MagicMock()
        mock_downloader = MagicMock()
        mock_media_cls.return_value = mock_downloader
        mock_status = MagicMock()
        mock_status.resumable_progress = 500
        mock_downloader.next_chunk.return_value = (mock_status, True)

        item = _make_item(
            name="Doc", mime_type="application/vnd.google-apps.document",
            size=None, md5=None,
        )
        result = _export_workspace(mock_service, item, dest)

        assert result.status == DownloadStatus.COMPLETED
        # Verify export_media was called with the right MIME
        mock_service.files.return_value.export_media.assert_called_once()
        export_call_kwargs = mock_service.files.return_value.export_media.call_args
        expected_mime = EXPORT_FORMATS["application/vnd.google-apps.document"][0]
        assert export_call_kwargs.kwargs.get("mimeType") == expected_mime

    @patch("gdrive_dl.downloader.requests")
    def test_fallback_to_export_links(self, mock_requests, tmp_path):
        """On exportSizeLimitExceeded, falls back to exportLinks."""
        import json

        from googleapiclient.errors import HttpError

        from gdrive_dl.downloader import _export_workspace

        dest = tmp_path / "BigDoc.docx"
        mock_service = MagicMock()

        # First attempt: export_media raises 403 exportSizeLimitExceeded
        resp = MagicMock()
        resp.status = 403
        error_body = json.dumps({
            "error": {"errors": [{"reason": "exportSizeLimitExceeded"}]}
        }).encode()
        mock_service.files.return_value.export_media.side_effect = HttpError(
            resp=resp, content=error_body,
        )

        # Mock the exportLinks on the item
        export_url = "https://docs.google.com/export/doc?id=d1"
        item = _make_item(
            file_id="d1", name="BigDoc",
            mime_type="application/vnd.google-apps.document",
            size=None, md5=None,
        )

        # Mock creds for Bearer token
        mock_creds = MagicMock()
        mock_creds.token = "test_token"

        # Mock requests.get for exportLinks fallback
        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"exported data"]
        mock_response.raise_for_status = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_requests.get.return_value = mock_response

        # Need to provide export links
        result = _export_workspace(
            mock_service, item, dest, creds=mock_creds,
            export_links={
                EXPORT_FORMATS["application/vnd.google-apps.document"][0]: export_url,
            },
        )

        assert result.status == DownloadStatus.COMPLETED

    def test_unknown_workspace_type_fails(self, tmp_path):
        """Workspace type not in EXPORT_FORMATS fails gracefully."""
        from gdrive_dl.downloader import _export_workspace

        dest = tmp_path / "unknown.bin"
        mock_service = MagicMock()

        item = _make_item(
            name="Unknown", mime_type="application/vnd.google-apps.unknown_type",
            size=None, md5=None,
        )
        result = _export_workspace(mock_service, item, dest)

        assert result.status == DownloadStatus.FAILED

    @patch("gdrive_dl.downloader.requests")
    def test_web_url_fallback_when_no_export_links(self, mock_requests, tmp_path):
        """On exportSizeLimitExceeded with no exportLinks, uses web export URL."""
        import json

        from googleapiclient.errors import HttpError

        from gdrive_dl.downloader import _export_workspace

        dest = tmp_path / "BigDoc.docx"
        mock_service = MagicMock()

        resp = MagicMock()
        resp.status = 403
        error_body = json.dumps({
            "error": {"errors": [{"reason": "exportSizeLimitExceeded"}]}
        }).encode()
        mock_service.files.return_value.export_media.side_effect = HttpError(
            resp=resp, content=error_body,
        )

        item = _make_item(
            file_id="d1", name="BigDoc",
            mime_type="application/vnd.google-apps.document",
            size=None, md5=None,
        )

        mock_creds = MagicMock()
        mock_creds.token = "test_token"

        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"exported data"]
        mock_response.raise_for_status = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_requests.get.return_value = mock_response

        # No export_links — should fall back to web export URL
        result = _export_workspace(
            mock_service, item, dest, creds=mock_creds,
            export_links=None,
        )

        assert result.status == DownloadStatus.COMPLETED
        # Verify the constructed URL
        call_url = mock_requests.get.call_args[0][0]
        assert "docs.google.com/document/d/d1/export" in call_url
        assert "format=docx" in call_url

    @patch("gdrive_dl.downloader.requests")
    def test_web_url_fallback_for_spreadsheet(self, mock_requests, tmp_path):
        """Web export URL fallback works for Google Sheets."""
        import json

        from googleapiclient.errors import HttpError

        from gdrive_dl.downloader import _export_workspace

        dest = tmp_path / "Sheet.xlsx"
        mock_service = MagicMock()

        resp = MagicMock()
        resp.status = 403
        error_body = json.dumps({
            "error": {"errors": [{"reason": "exportSizeLimitExceeded"}]}
        }).encode()
        mock_service.files.return_value.export_media.side_effect = HttpError(
            resp=resp, content=error_body,
        )

        item = _make_item(
            file_id="s1", name="Sheet",
            mime_type="application/vnd.google-apps.spreadsheet",
            size=None, md5=None,
        )

        mock_creds = MagicMock()
        mock_creds.token = "test_token"

        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"sheet data"]
        mock_response.raise_for_status = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_requests.get.return_value = mock_response

        result = _export_workspace(
            mock_service, item, dest, creds=mock_creds,
            export_links=None,
        )

        assert result.status == DownloadStatus.COMPLETED
        call_url = mock_requests.get.call_args[0][0]
        assert "docs.google.com/spreadsheets/d/s1/export" in call_url
        assert "format=xlsx" in call_url


# ---------------------------------------------------------------------------
# _resolve_export_url
# ---------------------------------------------------------------------------


class TestResolveExportUrl:
    """Export URL resolution: exportLinks → web URL → None."""

    def test_prefers_export_links_when_available(self):
        from gdrive_dl.downloader import _resolve_export_url

        item = _make_item(
            file_id="d1", mime_type="application/vnd.google-apps.document",
        )
        links = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document": "https://api-link"}
        url = _resolve_export_url(
            item, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", links,
        )
        assert url == "https://api-link"

    def test_falls_back_to_web_url_when_no_links(self):
        from gdrive_dl.downloader import _resolve_export_url

        item = _make_item(
            file_id="d1", mime_type="application/vnd.google-apps.document",
        )
        url = _resolve_export_url(
            item, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", None,
        )
        assert url == "https://docs.google.com/document/d/d1/export?format=docx"

    def test_returns_none_for_unknown_type(self):
        from gdrive_dl.downloader import _resolve_export_url

        item = _make_item(
            file_id="x1", mime_type="application/vnd.google-apps.script",
        )
        url = _resolve_export_url(
            item, "application/vnd.google-apps.script+json", None,
        )
        assert url is None
