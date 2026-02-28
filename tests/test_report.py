"""Tests for gdrive_dl.report — dry-run report generation."""

from __future__ import annotations

from gdrive_dl.constants import FOLDER_MIME
from gdrive_dl.report import DryRunReporter, format_bytes
from gdrive_dl.walker import DriveItem


def _item(
    file_id: str = "f1",
    name: str = "test.pdf",
    mime_type: str = "application/pdf",
    size: int | None = 1024,
    is_folder: bool = False,
    is_shortcut: bool = False,
    drive_path: str | None = None,
) -> DriveItem:
    return DriveItem(
        id=file_id,
        name=name,
        mime_type=mime_type,
        size=size,
        md5_checksum=None,
        created_time="2025-01-01T00:00:00.000Z",
        modified_time="2025-06-01T00:00:00.000Z",
        parents=["root"],
        drive_path=drive_path or name,
        is_folder=is_folder,
        can_download=True,
        is_shortcut=is_shortcut,
        shortcut_target_id="t1" if is_shortcut else None,
        shared_drive_id=None,
    )


# ---------------------------------------------------------------------------
# format_bytes
# ---------------------------------------------------------------------------


class TestFormatBytes:
    """Human-readable byte formatting."""

    def test_bytes(self):
        assert format_bytes(500) == "500 B"

    def test_kilobytes(self):
        assert format_bytes(1_500) == "1.5 KB"

    def test_megabytes(self):
        assert format_bytes(5_000_000) == "5.0 MB"

    def test_gigabytes(self):
        assert format_bytes(2_500_000_000) == "2.5 GB"

    def test_zero(self):
        assert format_bytes(0) == "0 B"


# ---------------------------------------------------------------------------
# DryRunReporter
# ---------------------------------------------------------------------------


class TestDryRunReporter:
    """Dry-run report generation from DriveItem lists."""

    def test_counts_folders(self):
        items = [
            _item(file_id="d1", name="SubDir", mime_type=FOLDER_MIME,
                  size=None, is_folder=True),
            _item(file_id="d2", name="SubDir2", mime_type=FOLDER_MIME,
                  size=None, is_folder=True),
            _item(file_id="f1", name="file.pdf", size=1024),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        stats = reporter._count_stats()
        assert stats["dir_count"] == 2
        assert stats["file_count"] == 1

    def test_counts_workspace_files(self):
        items = [
            _item(file_id="d1", name="Doc",
                  mime_type="application/vnd.google-apps.document", size=None),
            _item(file_id="f1", name="file.pdf", size=1024),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        stats = reporter._count_stats()
        assert stats["workspace_count"] == 1
        assert stats["file_count"] == 2  # workspace files are counted as files

    def test_counts_non_downloadable(self):
        items = [
            _item(file_id="form1", name="Survey",
                  mime_type="application/vnd.google-apps.form", size=None),
            _item(file_id="site1", name="Wiki",
                  mime_type="application/vnd.google-apps.site", size=None),
            _item(file_id="f1", name="file.pdf", size=1024),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        stats = reporter._count_stats()
        assert stats["non_downloadable_count"] == 2

    def test_size_estimate_sums_blob_sizes(self):
        items = [
            _item(file_id="f1", name="a.pdf", size=1000),
            _item(file_id="f2", name="b.pdf", size=2000),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        stats = reporter._count_stats()
        assert stats["total_size"] == 3000

    def test_workspace_size_not_counted(self):
        items = [
            _item(file_id="f1", name="a.pdf", size=1000),
            _item(file_id="d1", name="Doc",
                  mime_type="application/vnd.google-apps.document", size=None),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        stats = reporter._count_stats()
        assert stats["total_size"] == 1000

    def test_type_breakdown(self):
        items = [
            _item(file_id="f1", name="a.pdf", mime_type="application/pdf", size=500),
            _item(file_id="f2", name="b.pdf", mime_type="application/pdf", size=500),
            _item(file_id="f3", name="c.png", mime_type="image/png", size=200),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        breakdown = reporter._type_breakdown()
        # Should be sorted by count descending
        assert breakdown[0][0] == "application/pdf"
        assert breakdown[0][1] == 2
        assert breakdown[0][2] == 1000

    def test_non_downloadable_list(self):
        items = [
            _item(file_id="form1", name="Survey",
                  mime_type="application/vnd.google-apps.form",
                  size=None, drive_path="forms/Survey"),
            _item(file_id="f1", name="file.pdf", size=1024),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        nd = reporter._non_downloadable_list()
        assert len(nd) == 1
        assert nd[0][0] == "forms/Survey"
        assert nd[0][1] == "application/vnd.google-apps.form"

    def test_generate_returns_string(self):
        items = [
            _item(file_id="f1", name="file.pdf", size=1024),
        ]
        reporter = DryRunReporter(items, "Root", "root123")
        output = reporter.generate()
        assert "Root" in output
        assert "root123" in output

    def test_empty_items(self):
        reporter = DryRunReporter([], "Empty", "e123")
        stats = reporter._count_stats()
        assert stats["dir_count"] == 0
        assert stats["file_count"] == 0
        assert stats["total_size"] == 0

    def test_generate_no_crash_with_mixed_items(self):
        """Smoke test: generate() handles all item types without crashing."""
        items = [
            _item(file_id="d1", name="Dir", mime_type=FOLDER_MIME,
                  size=None, is_folder=True),
            _item(file_id="f1", name="a.pdf", size=5000),
            _item(file_id="w1", name="Doc",
                  mime_type="application/vnd.google-apps.document", size=None),
            _item(file_id="nd1", name="Form",
                  mime_type="application/vnd.google-apps.form", size=None),
        ]
        reporter = DryRunReporter(items, "Project", "p123")
        output = reporter.generate()
        assert isinstance(output, str)
        assert len(output) > 0
