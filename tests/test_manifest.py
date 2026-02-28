"""Tests for gdrive_dl.manifest — download tracking with atomic persistence."""

import json
import time

import pytest

from gdrive_dl.exceptions import ManifestError
from gdrive_dl.manifest import SCHEMA_VERSION, DownloadStatus, Manifest


class TestDownloadStatus:
    """DownloadStatus enum values serialize cleanly to JSON."""

    def test_all_statuses_are_strings(self):
        """Each status .value is a lowercase string."""
        for status in DownloadStatus:
            assert isinstance(status.value, str)
            assert status.value == status.value.lower()

    def test_expected_members(self):
        """All required statuses exist."""
        names = {s.name for s in DownloadStatus}
        expected = {"PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "SKIPPED", "CHECKSUM_FAILED"}
        assert names >= expected


class TestManifestCreate:
    """Manifest.load_or_create with no existing file."""

    def test_creates_fresh_manifest(self, tmp_path):
        """New manifest has schema version and empty files dict."""
        path = str(tmp_path / "manifest.json")
        m = Manifest.load_or_create(path)

        assert m._data["schemaVersion"] == SCHEMA_VERSION
        assert m._data["files"] == {}
        assert "sessionId" in m._data
        assert "createdAt" in m._data

    def test_fresh_manifest_not_saved_until_explicit(self, tmp_path):
        """Creating a manifest doesn't write to disk yet."""
        path = tmp_path / "manifest.json"
        Manifest.load_or_create(str(path))

        assert not path.exists()


class TestManifestLoad:
    """Manifest.load_or_create with existing file."""

    def test_loads_existing_manifest(self, tmp_path):
        """Loading preserves file entries from disk."""
        path = tmp_path / "manifest.json"
        data = {
            "schemaVersion": SCHEMA_VERSION,
            "sessionId": "test-session",
            "createdAt": "2024-01-01T00:00:00+00:00",
            "updatedAt": "2024-01-01T00:00:00+00:00",
            "files": {
                "file1": {"fileId": "file1", "status": "completed"},
            },
        }
        path.write_text(json.dumps(data))

        m = Manifest.load_or_create(str(path))
        assert m._data["files"]["file1"]["status"] == "completed"

    def test_corrupt_json_raises_manifest_error(self, tmp_path):
        """Invalid JSON raises ManifestError."""
        path = tmp_path / "manifest.json"
        path.write_text("{corrupt json!!!")

        with pytest.raises(ManifestError, match="Corrupt"):
            Manifest.load_or_create(str(path))

    def test_incompatible_schema_raises_manifest_error(self, tmp_path):
        """Wrong schema version raises ManifestError."""
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({"schemaVersion": 999, "files": {}}))

        with pytest.raises(ManifestError, match="schema"):
            Manifest.load_or_create(str(path))


class TestManifestUpdateFile:
    """Manifest.update_file tracks per-file status."""

    def test_update_creates_entry(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file("f1", DownloadStatus.IN_PROGRESS, name="test.pdf")

        assert m._data["files"]["f1"]["status"] == "in_progress"
        assert m._data["files"]["f1"]["name"] == "test.pdf"

    def test_update_overwrites_status(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file("f1", DownloadStatus.IN_PROGRESS)
        m.update_file("f1", DownloadStatus.COMPLETED)

        assert m._data["files"]["f1"]["status"] == "completed"

    def test_update_preserves_extra_kwargs(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file(
            "f1", DownloadStatus.COMPLETED, localPath="/out/test.pdf", bytesDownloaded=1024,
        )

        entry = m._data["files"]["f1"]
        assert entry["localPath"] == "/out/test.pdf"
        assert entry["bytesDownloaded"] == 1024


class TestManifestIsCompleted:
    """Manifest.is_completed checks for COMPLETED status."""

    def test_completed_returns_true(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file("f1", DownloadStatus.COMPLETED)

        assert m.is_completed("f1") is True

    def test_in_progress_returns_false(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file("f1", DownloadStatus.IN_PROGRESS)

        assert m.is_completed("f1") is False

    def test_missing_file_returns_false(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))

        assert m.is_completed("nonexistent") is False


class TestManifestSave:
    """Manifest.save writes atomically to disk."""

    def test_save_writes_valid_json(self, tmp_path):
        path = tmp_path / "manifest.json"
        m = Manifest.load_or_create(str(path))
        m.update_file("f1", DownloadStatus.COMPLETED)
        m.save()

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["files"]["f1"]["status"] == "completed"

    def test_save_is_atomic_no_partial_on_disk(self, tmp_path):
        """After save, no .tmp files remain."""
        path = tmp_path / "manifest.json"
        m = Manifest.load_or_create(str(path))
        m.update_file("f1", DownloadStatus.COMPLETED)
        m.save()

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_no_op_save_when_not_dirty(self, tmp_path):
        """Saving without changes doesn't write."""
        path = tmp_path / "manifest.json"
        m = Manifest.load_or_create(str(path))
        m.save()

        assert not path.exists()

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "manifest.json"
        m = Manifest.load_or_create(str(path))
        m.update_file("f1", DownloadStatus.COMPLETED)
        m.save()

        assert path.exists()


class TestManifestAutoFlush:
    """Manifest auto-flushes on completion thresholds."""

    def test_flushes_after_n_completions(self, tmp_path):
        """After 10 completions, manifest is auto-flushed."""
        path = tmp_path / "manifest.json"
        m = Manifest.load_or_create(str(path))

        for i in range(10):
            m.update_file(f"f{i}", DownloadStatus.COMPLETED)

        assert path.exists()

    def test_flushes_after_time_threshold(self, tmp_path):
        """After 30 seconds elapsed, manifest is auto-flushed."""
        path = tmp_path / "manifest.json"
        m = Manifest.load_or_create(str(path))
        # Simulate time passing
        m._last_flush_time = time.monotonic() - 31.0
        m.update_file("f1", DownloadStatus.IN_PROGRESS)

        assert path.exists()


class TestManifestGetFile:
    """Manifest.get_file returns entry dict or None."""

    def test_returns_entry(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file("f1", DownloadStatus.COMPLETED, name="test.pdf")

        entry = m.get_file("f1")
        assert entry is not None
        assert entry["name"] == "test.pdf"

    def test_returns_none_for_missing(self, tmp_path):
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))

        assert m.get_file("nonexistent") is None


class TestManifestResume:
    """Resume diff: is_completed_and_unchanged compares status + modifiedTime."""

    def test_completed_and_unchanged_true(self, tmp_path):
        """Completed file with same modifiedTime returns True."""
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file(
            "f1", DownloadStatus.COMPLETED,
            modifiedTime="2024-06-01T00:00:00.000Z",
        )

        assert m.is_completed_and_unchanged("f1", "2024-06-01T00:00:00.000Z") is True

    def test_completed_but_changed_false(self, tmp_path):
        """Completed file with different modifiedTime returns False."""
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file(
            "f1", DownloadStatus.COMPLETED,
            modifiedTime="2024-06-01T00:00:00.000Z",
        )

        assert m.is_completed_and_unchanged("f1", "2024-07-01T00:00:00.000Z") is False

    def test_not_completed_false(self, tmp_path):
        """Failed file returns False regardless of modifiedTime."""
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))
        m.update_file(
            "f1", DownloadStatus.FAILED,
            modifiedTime="2024-06-01T00:00:00.000Z",
        )

        assert m.is_completed_and_unchanged("f1", "2024-06-01T00:00:00.000Z") is False

    def test_missing_file_false(self, tmp_path):
        """File not in manifest returns False."""
        m = Manifest.load_or_create(str(tmp_path / "manifest.json"))

        assert m.is_completed_and_unchanged("nonexistent", "2024-06-01T00:00:00.000Z") is False


class TestManifestSchemaValidation:
    """Enhanced schema version validation."""

    def test_missing_schema_version_raises(self, tmp_path):
        """Manifest with no schemaVersion raises ManifestError."""
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({"files": {}}))

        with pytest.raises(ManifestError, match="[Ss]chema"):
            Manifest.load_or_create(str(path))

    def test_too_new_schema_raises_with_upgrade_message(self, tmp_path):
        """Schema version newer than supported suggests upgrade."""
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps({"schemaVersion": 999, "files": {}}))

        with pytest.raises(ManifestError, match="[Uu]pgrade|[Nn]ewer|[Ii]ncompatible"):
            Manifest.load_or_create(str(path))
