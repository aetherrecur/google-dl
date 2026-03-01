"""Tests for gdrive_dl.walker — BFS directory traversal and DriveItem mapping."""



from gdrive_dl.constants import FOLDER_MIME, SHORTCUT_MIME
from gdrive_dl.walker import DriveItem, _build_drive_item, _deduplicate_names, walk
from tests.conftest import make_file_item, make_folder_item, make_shortcut_item

# ---------------------------------------------------------------------------
# DriveItem dataclass
# ---------------------------------------------------------------------------


class TestDriveItem:
    """DriveItem property tests."""

    def test_is_workspace_file_for_doc(self):
        item = DriveItem(
            id="1", name="Doc", mime_type="application/vnd.google-apps.document",
            size=None, md5_checksum=None, created_time="", modified_time="",
            parents=[], drive_path="Doc", is_folder=False, can_download=True,
            is_shortcut=False, shortcut_target_id=None, shared_drive_id=None,
            export_links=None,
        )
        assert item.is_workspace_file is True

    def test_is_workspace_file_false_for_pdf(self):
        item = DriveItem(
            id="1", name="Doc.pdf", mime_type="application/pdf",
            size=1024, md5_checksum="abc", created_time="", modified_time="",
            parents=[], drive_path="Doc.pdf", is_folder=False, can_download=True,
            is_shortcut=False, shortcut_target_id=None, shared_drive_id=None,
            export_links=None,
        )
        assert item.is_workspace_file is False

    def test_is_workspace_file_false_for_folder(self):
        item = DriveItem(
            id="1", name="Folder", mime_type=FOLDER_MIME,
            size=None, md5_checksum=None, created_time="", modified_time="",
            parents=[], drive_path="Folder", is_folder=True, can_download=True,
            is_shortcut=False, shortcut_target_id=None, shared_drive_id=None,
            export_links=None,
        )
        assert item.is_workspace_file is False

    def test_is_workspace_file_false_for_shortcut(self):
        item = DriveItem(
            id="1", name="SC", mime_type=SHORTCUT_MIME,
            size=None, md5_checksum=None, created_time="", modified_time="",
            parents=[], drive_path="SC", is_folder=False, can_download=True,
            is_shortcut=True, shortcut_target_id="t1", shared_drive_id=None,
            export_links=None,
        )
        assert item.is_workspace_file is False


# ---------------------------------------------------------------------------
# _build_drive_item
# ---------------------------------------------------------------------------


class TestBuildDriveItem:
    """API response is correctly mapped to DriveItem dataclass."""

    def test_maps_all_fields(self):
        from pathlib import Path
        raw = make_file_item(file_id="f1", name="report.pdf", size="2048", md5="deadbeef")
        item = _build_drive_item(raw, Path("Legal"))

        assert item.id == "f1"
        assert item.name == "report.pdf"
        assert item.mime_type == "application/pdf"
        assert item.size == 2048
        assert item.md5_checksum == "deadbeef"
        assert item.drive_path == "Legal/report.pdf"
        assert item.is_folder is False
        assert item.can_download is True

    def test_workspace_file_has_no_size(self):
        from pathlib import Path
        raw = make_file_item(
            file_id="d1", name="Doc", mime_type="application/vnd.google-apps.document",
            size=None, md5=None,
        )
        item = _build_drive_item(raw, Path())

        assert item.size is None
        assert item.md5_checksum is None
        assert item.drive_path == "Doc"

    def test_folder_item(self):
        from pathlib import Path
        raw = make_folder_item(file_id="folder1", name="Photos")
        item = _build_drive_item(raw, Path("My Drive"))

        assert item.is_folder is True
        assert item.drive_path == "My Drive/Photos"

    def test_shared_drive_id(self):
        from pathlib import Path
        raw = make_file_item(drive_id="shared123")
        item = _build_drive_item(raw, Path())

        assert item.shared_drive_id == "shared123"

    def test_export_links_populated(self):
        from pathlib import Path
        links = {"application/pdf": "https://export-link"}
        raw = make_file_item(
            mime_type="application/vnd.google-apps.document",
            export_links=links,
        )
        item = _build_drive_item(raw, Path())

        assert item.export_links == links

    def test_export_links_none_when_absent(self):
        from pathlib import Path
        raw = make_file_item()
        item = _build_drive_item(raw, Path())

        assert item.export_links is None


# ---------------------------------------------------------------------------
# _deduplicate_names
# ---------------------------------------------------------------------------


class TestDeduplicateNames:
    """Duplicate names in same folder get __{id[:8]} suffix."""

    def test_no_duplicates_unchanged(self):
        items = [
            make_file_item(file_id="a", name="file1.pdf"),
            make_file_item(file_id="b", name="file2.pdf"),
        ]
        result = _deduplicate_names(items)

        assert result[0]["name"] == "file1.pdf"
        assert result[1]["name"] == "file2.pdf"

    def test_duplicates_get_suffix(self):
        items = [
            make_file_item(file_id="abc12345xxx", name="report.pdf"),
            make_file_item(file_id="def67890yyy", name="report.pdf"),
        ]
        result = _deduplicate_names(items)

        assert result[0]["name"] == "report.pdf__abc12345"
        assert result[1]["name"] == "report.pdf__def67890"

    def test_original_items_not_mutated(self):
        items = [
            make_file_item(file_id="abc12345xxx", name="same.txt"),
            make_file_item(file_id="def67890yyy", name="same.txt"),
        ]
        _deduplicate_names(items)

        assert items[0]["name"] == "same.txt"
        assert items[1]["name"] == "same.txt"


# ---------------------------------------------------------------------------
# walk — BFS traversal
# ---------------------------------------------------------------------------


class TestWalk:
    """walk() performs BFS and returns flat list of DriveItems."""

    def test_single_folder_with_files(self, mock_service):
        """Walk a folder with 3 files returns 3 DriveItems."""
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                make_file_item(file_id="f1", name="a.pdf"),
                make_file_item(file_id="f2", name="b.pdf"),
                make_file_item(file_id="f3", name="c.pdf"),
            ],
        }

        items = walk(mock_service, "root_folder")
        assert len(items) == 3
        assert {i.name for i in items} == {"a.pdf", "b.pdf", "c.pdf"}

    def test_nested_folders_build_correct_paths(self, mock_service):
        """BFS traversal of nested folders builds correct drive_path."""
        # First call: root folder contains a subfolder and a file
        # Second call: subfolder contains a file
        mock_service.files.return_value.list.return_value.execute.side_effect = [
            {
                "files": [
                    make_folder_item(file_id="sub1", name="SubDir"),
                    make_file_item(file_id="f1", name="root_file.pdf"),
                ],
            },
            {
                "files": [
                    make_file_item(file_id="f2", name="nested_file.pdf"),
                ],
            },
        ]

        items = walk(mock_service, "root_folder")

        paths = {i.drive_path for i in items if not i.is_folder}
        assert "root_file.pdf" in paths
        assert "SubDir/nested_file.pdf" in paths

    def test_pagination(self, mock_service):
        """When API returns nextPageToken, fetches subsequent pages."""
        mock_service.files.return_value.list.return_value.execute.side_effect = [
            {
                "files": [make_file_item(file_id="f1", name="page1.pdf")],
                "nextPageToken": "token2",
            },
            {
                "files": [make_file_item(file_id="f2", name="page2.pdf")],
            },
        ]

        items = walk(mock_service, "root_folder")
        assert len(items) == 2
        assert {i.name for i in items} == {"page1.pdf", "page2.pdf"}

    def test_shortcut_resolution(self, mock_service):
        """Shortcuts resolve to target file with separate files.get call."""
        shortcut = make_shortcut_item(
            file_id="sc1", name="My Link", target_id="target1",
        )
        target_response = make_file_item(file_id="target1", name="Real File.pdf")

        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [shortcut],
        }
        mock_service.files.return_value.get.return_value.execute.return_value = target_response

        items = walk(mock_service, "root_folder")
        assert len(items) == 1
        assert items[0].id == "target1"
        assert items[0].name == "Real File.pdf"

    def test_shortcut_cycle_detection(self, mock_service):
        """Circular shortcut references don't cause infinite loop."""
        # Shortcut pointing back to the root folder
        shortcut = make_shortcut_item(
            file_id="sc1", name="Cycle", target_id="root_folder",
        )
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [shortcut],
        }

        items = walk(mock_service, "root_folder")
        # The cycle shortcut should be skipped
        assert len(items) == 0

    def test_name_collision_in_same_folder(self, mock_service):
        """Duplicate names in same folder get __{id[:8]} suffix."""
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                make_file_item(file_id="abc12345xxx", name="report.pdf"),
                make_file_item(file_id="def67890yyy", name="report.pdf"),
            ],
        }

        items = walk(mock_service, "root_folder")
        names = {i.name for i in items}
        assert "report.pdf__abc12345" in names
        assert "report.pdf__def67890" in names

    def test_shared_drive_kwargs_included(self, mock_service):
        """API calls include supportsAllDrives and includeItemsFromAllDrives."""
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [],
        }

        walk(mock_service, "root_folder")

        call_kwargs = mock_service.files.return_value.list.call_args
        assert call_kwargs.kwargs.get("supportsAllDrives") is True
        assert call_kwargs.kwargs.get("includeItemsFromAllDrives") is True

    def test_empty_folder(self, mock_service):
        """Walking an empty folder returns empty list."""
        mock_service.files.return_value.list.return_value.execute.return_value = {
            "files": [],
        }

        items = walk(mock_service, "root_folder")
        assert items == []

    def test_folders_included_in_results(self, mock_service):
        """Subfolder items are included in results with is_folder=True."""
        mock_service.files.return_value.list.return_value.execute.side_effect = [
            {"files": [make_folder_item(file_id="sub1", name="Sub")]},
            {"files": []},
        ]

        items = walk(mock_service, "root_folder")
        assert len(items) == 1
        assert items[0].is_folder is True
        assert items[0].name == "Sub"
