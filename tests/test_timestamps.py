"""Tests for gdrive_dl.timestamps — Drive timestamp preservation via os.utime."""

import os
from datetime import datetime, timezone

from gdrive_dl.timestamps import _parse_rfc3339, apply_timestamps


class TestParseRfc3339:
    """_parse_rfc3339 converts Drive timestamps to POSIX float."""

    def test_z_suffix(self):
        """Handles Google's 'Z' UTC suffix."""
        ts = _parse_rfc3339("2024-03-15T10:30:00.000Z")
        dt = datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert abs(ts - dt.timestamp()) < 0.001

    def test_offset_suffix(self):
        """Handles explicit +00:00 offset."""
        ts = _parse_rfc3339("2024-03-15T10:30:00+00:00")
        dt = datetime(2024, 3, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert abs(ts - dt.timestamp()) < 0.001

    def test_milliseconds_preserved(self):
        """Milliseconds in timestamp are preserved."""
        ts = _parse_rfc3339("2024-06-01T12:00:00.500Z")
        dt = datetime(2024, 6, 1, 12, 0, 0, 500000, tzinfo=timezone.utc)
        assert abs(ts - dt.timestamp()) < 0.001


class TestApplyTimestamps:
    """apply_timestamps sets mtime and atime on local files."""

    def test_mtime_set_from_modified_time(self, tmp_path):
        """File mtime matches Drive modifiedTime after apply_timestamps."""
        file = tmp_path / "test.txt"
        file.write_text("content")

        modified = "2024-01-15T08:30:00.000Z"
        apply_timestamps(file, modified_time=modified)

        stat = os.stat(file)
        expected_mtime = datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc).timestamp()
        assert abs(stat.st_mtime - expected_mtime) < 1.0

    def test_atime_set_from_created_time(self, tmp_path):
        """File atime matches Drive createdTime when provided."""
        file = tmp_path / "test.txt"
        file.write_text("content")

        created = "2024-01-10T12:00:00.000Z"
        modified = "2024-01-15T08:30:00.000Z"
        apply_timestamps(file, modified_time=modified, created_time=created)

        stat = os.stat(file)
        expected_atime = datetime(2024, 1, 10, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        assert abs(stat.st_atime - expected_atime) < 1.0

    def test_atime_falls_back_to_mtime(self, tmp_path):
        """When created_time is None, atime is set to modifiedTime."""
        file = tmp_path / "test.txt"
        file.write_text("content")

        modified = "2024-01-15T08:30:00.000Z"
        apply_timestamps(file, modified_time=modified, created_time=None)

        stat = os.stat(file)
        expected = datetime(2024, 1, 15, 8, 30, 0, tzinfo=timezone.utc).timestamp()
        assert abs(stat.st_atime - expected) < 1.0
        assert abs(stat.st_mtime - expected) < 1.0

    def test_works_on_directories(self, tmp_path):
        """Timestamps can be applied to directories too."""
        dir_path = tmp_path / "subdir"
        dir_path.mkdir()

        modified = "2024-06-01T00:00:00.000Z"
        apply_timestamps(dir_path, modified_time=modified)

        stat = os.stat(dir_path)
        expected = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp()
        assert abs(stat.st_mtime - expected) < 1.0
