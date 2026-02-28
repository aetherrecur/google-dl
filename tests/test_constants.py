"""Tests for gdrive_dl.constants — MIME types, export formats, and defaults."""

from gdrive_dl.constants import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_RETRIES,
    EXPORT_FORMATS,
    FOLDER_MIME,
    NON_DOWNLOADABLE,
    SCOPES,
    SHORTCUT_MIME,
)


class TestFolderAndShortcutMime:
    """Core MIME type constants match Google Drive API values."""

    def test_folder_mime(self):
        assert FOLDER_MIME == "application/vnd.google-apps.folder"

    def test_shortcut_mime(self):
        assert SHORTCUT_MIME == "application/vnd.google-apps.shortcut"


class TestScopes:
    """OAuth scopes are minimal and read-only."""

    def test_scopes_contains_readonly(self):
        assert "https://www.googleapis.com/auth/drive.readonly" in SCOPES

    def test_scopes_has_exactly_one_entry(self):
        assert len(SCOPES) == 1

    def test_scopes_does_not_include_write(self):
        for scope in SCOPES:
            assert "drive.readonly" in scope or "drive.metadata" in scope
            assert scope != "https://www.googleapis.com/auth/drive"


class TestExportFormats:
    """EXPORT_FORMATS covers all exportable Workspace types."""

    def test_covers_google_docs(self):
        key = "application/vnd.google-apps.document"
        assert key in EXPORT_FORMATS
        mime, ext = EXPORT_FORMATS[key]
        assert ext == ".docx"

    def test_covers_google_sheets(self):
        key = "application/vnd.google-apps.spreadsheet"
        assert key in EXPORT_FORMATS
        mime, ext = EXPORT_FORMATS[key]
        assert ext == ".xlsx"

    def test_covers_google_slides(self):
        key = "application/vnd.google-apps.presentation"
        assert key in EXPORT_FORMATS
        mime, ext = EXPORT_FORMATS[key]
        assert ext == ".pptx"

    def test_covers_google_drawings(self):
        key = "application/vnd.google-apps.drawing"
        assert key in EXPORT_FORMATS
        mime, ext = EXPORT_FORMATS[key]
        assert ext == ".pdf"

    def test_covers_apps_script(self):
        key = "application/vnd.google-apps.script"
        assert key in EXPORT_FORMATS
        mime, ext = EXPORT_FORMATS[key]
        assert ext == ".json"

    def test_all_entries_have_mime_and_extension(self):
        for workspace_mime, (export_mime, ext) in EXPORT_FORMATS.items():
            assert workspace_mime.startswith("application/vnd.google-apps.")
            assert isinstance(export_mime, str)
            assert ext.startswith(".")

    def test_has_at_least_five_entries(self):
        assert len(EXPORT_FORMATS) >= 5


class TestNonDownloadable:
    """NON_DOWNLOADABLE set contains types that cannot be exported."""

    def test_contains_forms(self):
        assert "application/vnd.google-apps.form" in NON_DOWNLOADABLE

    def test_contains_sites(self):
        assert "application/vnd.google-apps.site" in NON_DOWNLOADABLE

    def test_contains_maps(self):
        assert "application/vnd.google-apps.map" in NON_DOWNLOADABLE

    def test_contains_fusiontable(self):
        assert "application/vnd.google-apps.fusiontable" in NON_DOWNLOADABLE

    def test_contains_folder(self):
        assert FOLDER_MIME in NON_DOWNLOADABLE

    def test_contains_shortcut(self):
        assert SHORTCUT_MIME in NON_DOWNLOADABLE

    def test_contains_drive_sdk(self):
        assert "application/vnd.google-apps.drive-sdk" in NON_DOWNLOADABLE

    def test_no_overlap_with_export_formats(self):
        """Nothing in NON_DOWNLOADABLE should also be in EXPORT_FORMATS."""
        overlap = set(NON_DOWNLOADABLE) & set(EXPORT_FORMATS.keys())
        assert overlap == set()

    def test_is_a_set(self):
        assert isinstance(NON_DOWNLOADABLE, (set, frozenset))


class TestDefaults:
    """Default configuration constants have expected values."""

    def test_default_page_size(self):
        assert DEFAULT_PAGE_SIZE == 1000

    def test_default_retries(self):
        assert DEFAULT_RETRIES == 5

    def test_default_chunk_size(self):
        assert DEFAULT_CHUNK_SIZE == 5 * 1024 * 1024

    def test_chunk_size_is_multiple_of_256kb(self):
        """Google API requires chunk size to be a multiple of 256 KB."""
        assert (DEFAULT_CHUNK_SIZE % (256 * 1024)) == 0
