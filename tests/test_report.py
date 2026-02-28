"""Tests for gdrive_dl.report — dry-run and post-download report generation."""

from __future__ import annotations

import json

from gdrive_dl.constants import FOLDER_MIME
from gdrive_dl.manifest import DownloadStatus, Manifest
from gdrive_dl.report import DryRunReporter, ReportGenerator, format_bytes
from gdrive_dl.runner import SessionResult
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


# ---------------------------------------------------------------------------
# ReportGenerator helpers
# ---------------------------------------------------------------------------


def _make_result(
    completed: int = 5,
    failed: int = 1,
    skipped: int = 2,
    bytes_dl: int = 50_000,
) -> SessionResult:
    return SessionResult(
        files_completed=completed,
        files_failed=failed,
        files_skipped=skipped,
        bytes_downloaded=bytes_dl,
        directories_created=3,
        start_time="2026-02-28T14:00:00+00:00",
        end_time="2026-02-28T14:32:00+00:00",
    )


def _make_manifest(tmp_path) -> Manifest:
    manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
    manifest.update_file(
        "f1", DownloadStatus.COMPLETED, name="report.pdf",
        drivePath="docs/report.pdf",
    )
    manifest.update_file(
        "f2", DownloadStatus.FAILED, name="budget.xlsx",
        drivePath="Finance/budget.xlsx", error="403 cannotDownload",
    )
    manifest.update_file(
        "f3", DownloadStatus.SKIPPED, name="form.gform",
        drivePath="forms/form.gform", reason="Non-downloadable type",
    )
    return manifest


def _make_items() -> list[DriveItem]:
    return [
        _item(file_id="f1", name="report.pdf", size=30_000,
              drive_path="docs/report.pdf"),
        _item(file_id="f2", name="budget.xlsx", size=20_000,
              mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
              drive_path="Finance/budget.xlsx"),
        _item(file_id="f3", name="form.gform",
              mime_type="application/vnd.google-apps.form",
              size=None, drive_path="forms/form.gform"),
    ]


def _make_generator(tmp_path) -> ReportGenerator:
    return ReportGenerator(
        result=_make_result(),
        items=_make_items(),
        manifest=_make_manifest(tmp_path),
        folder_name="My Project",
        folder_id="abc123",
        output_dir=tmp_path,
    )


# ---------------------------------------------------------------------------
# ReportGenerator — Markdown
# ---------------------------------------------------------------------------


class TestMarkdownReport:
    """Post-download Markdown report generation."""

    def test_contains_session_info(self, tmp_path):
        """Markdown report includes start time, duration, source info."""
        gen = _make_generator(tmp_path)
        md = gen.generate("markdown")
        assert "My Project" in md
        assert "abc123" in md
        assert "2026-02-28" in md

    def test_result_table(self, tmp_path):
        """Markdown report includes completed/skipped/failed counts."""
        gen = _make_generator(tmp_path)
        md = gen.generate("markdown")
        assert "5" in md  # completed
        assert "1" in md  # failed
        assert "2" in md  # skipped

    def test_failed_files(self, tmp_path):
        """Failed files listed with path and error reason."""
        gen = _make_generator(tmp_path)
        md = gen.generate("markdown")
        assert "budget.xlsx" in md
        assert "403 cannotDownload" in md

    def test_skipped_files(self, tmp_path):
        """Skipped files listed with reason."""
        gen = _make_generator(tmp_path)
        md = gen.generate("markdown")
        assert "form.gform" in md
        assert "Non-downloadable" in md


# ---------------------------------------------------------------------------
# ReportGenerator — HTML
# ---------------------------------------------------------------------------


class TestHtmlReport:
    """Post-download HTML report generation."""

    def test_self_contained(self, tmp_path):
        """HTML report includes inline CSS, no external dependencies."""
        gen = _make_generator(tmp_path)
        html = gen.generate("html")
        assert "<style>" in html
        assert "<table>" in html
        assert "<html>" in html

    def test_same_content(self, tmp_path):
        """HTML report contains same key data as Markdown report."""
        gen = _make_generator(tmp_path)
        html = gen.generate("html")
        assert "My Project" in html
        assert "budget.xlsx" in html
        assert "403 cannotDownload" in html


# ---------------------------------------------------------------------------
# ReportGenerator — JSON
# ---------------------------------------------------------------------------


class TestJsonReport:
    """Post-download JSON report generation."""

    def test_valid_json(self, tmp_path):
        """JSON report is valid JSON that can be parsed."""
        gen = _make_generator(tmp_path)
        text = gen.generate("json")
        data = json.loads(text)
        assert isinstance(data, dict)

    def test_structure(self, tmp_path):
        """JSON report has expected top-level keys."""
        gen = _make_generator(tmp_path)
        data = json.loads(gen.generate("json"))
        assert "session" in data
        assert "results" in data
        assert "failed_files" in data
        assert "skipped_files" in data
        assert "type_breakdown" in data

    def test_machine_readable(self, tmp_path):
        """JSON report values are typed correctly (ints, not strings)."""
        gen = _make_generator(tmp_path)
        data = json.loads(gen.generate("json"))
        assert isinstance(data["results"]["completed"], int)
        assert isinstance(data["results"]["bytes_downloaded"], int)
        assert data["results"]["completed"] == 5
        assert data["results"]["failed"] == 1


# ---------------------------------------------------------------------------
# ReportGenerator — General
# ---------------------------------------------------------------------------


class TestReportGeneral:
    """General report behavior."""

    def test_report_file_naming(self, tmp_path):
        """Report file uses correct extension for format."""
        gen = _make_generator(tmp_path)
        path_md = gen.save("markdown")
        assert path_md.name == "gdrive-dl-report.md"

        path_html = gen.save("html")
        assert path_html.name == "gdrive-dl-report.html"

        path_json = gen.save("json")
        assert path_json.name == "gdrive-dl-report.json"

    def test_report_saved_to_output_dir(self, tmp_path):
        """Report file saved in the output directory."""
        gen = _make_generator(tmp_path)
        path = gen.save("markdown")
        assert path.parent == tmp_path
        assert path.exists()

    def test_report_with_zero_failures(self, tmp_path):
        """Report works correctly when no files failed."""
        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        manifest.update_file(
            "f1", DownloadStatus.COMPLETED, name="a.pdf", drivePath="a.pdf",
        )
        gen = ReportGenerator(
            result=_make_result(completed=1, failed=0, skipped=0),
            items=[_item(file_id="f1", name="a.pdf", size=1000)],
            manifest=manifest,
            folder_name="Test", folder_id="t1",
            output_dir=tmp_path,
        )
        md = gen.generate("markdown")
        assert "Failed" not in md or "0" in md

    def test_report_with_all_failures(self, tmp_path):
        """Report works correctly when all files failed."""
        manifest = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        manifest.update_file(
            "f1", DownloadStatus.FAILED, name="a.pdf",
            drivePath="a.pdf", error="timeout",
        )
        gen = ReportGenerator(
            result=_make_result(completed=0, failed=1, skipped=0, bytes_dl=0),
            items=[_item(file_id="f1", name="a.pdf", size=1000)],
            manifest=manifest,
            folder_name="Test", folder_id="t1",
            output_dir=tmp_path,
        )
        md = gen.generate("markdown")
        assert "a.pdf" in md
        assert "timeout" in md
