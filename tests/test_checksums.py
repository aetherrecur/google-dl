"""Tests for gdrive_dl.checksums — MD5 verification of downloaded files."""

import hashlib

import pytest

from gdrive_dl.checksums import verify_checksum
from gdrive_dl.exceptions import ChecksumError


class TestVerifyChecksum:
    """verify_checksum validates MD5 of downloaded files."""

    def test_matching_md5_returns_true(self, tmp_path):
        """File with matching MD5 checksum returns True."""
        file = tmp_path / "test.bin"
        content = b"hello world"
        file.write_bytes(content)
        expected = hashlib.md5(content).hexdigest()

        assert verify_checksum(file, expected) is True

    def test_mismatched_md5_raises_checksum_error(self, tmp_path):
        """File with wrong MD5 raises ChecksumError."""
        file = tmp_path / "test.bin"
        file.write_bytes(b"hello world")

        with pytest.raises(ChecksumError) as exc_info:
            verify_checksum(
                file, "0000000000000000000000000000dead", file_id="abc", name="test.bin",
            )

        assert exc_info.value.file_id == "abc"
        assert exc_info.value.expected == "0000000000000000000000000000dead"

    def test_none_checksum_returns_true(self, tmp_path):
        """Workspace files have no MD5 — None returns True (always passes)."""
        file = tmp_path / "doc.docx"
        file.write_bytes(b"exported content")

        assert verify_checksum(file, None) is True

    def test_empty_file_checksum(self, tmp_path):
        """Empty file has a valid MD5 that can be verified."""
        file = tmp_path / "empty.bin"
        file.write_bytes(b"")
        expected = hashlib.md5(b"").hexdigest()

        assert verify_checksum(file, expected) is True

    def test_large_file_checksum(self, tmp_path):
        """Files larger than buffer size are checksummed correctly."""
        file = tmp_path / "large.bin"
        # 256 KB of data — larger than typical buffer sizes
        content = b"x" * (256 * 1024)
        file.write_bytes(content)
        expected = hashlib.md5(content).hexdigest()

        assert verify_checksum(file, expected) is True

    def test_checksum_error_includes_actual(self, tmp_path):
        """ChecksumError stores both expected and actual hash."""
        file = tmp_path / "test.bin"
        content = b"test data"
        file.write_bytes(content)
        actual_md5 = hashlib.md5(content).hexdigest()

        with pytest.raises(ChecksumError) as exc_info:
            verify_checksum(file, "wrong_hash", file_id="f1", name="test.bin")

        assert exc_info.value.actual == actual_md5

    def test_file_id_and_name_optional(self, tmp_path):
        """file_id and name default to empty string when not provided."""
        file = tmp_path / "test.bin"
        file.write_bytes(b"data")

        with pytest.raises(ChecksumError) as exc_info:
            verify_checksum(file, "wrong")

        assert exc_info.value.file_id == ""
        assert exc_info.value.name == ""
