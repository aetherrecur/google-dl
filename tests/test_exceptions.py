"""Tests for gdrive_dl.exceptions — exception hierarchy and error context."""

import pytest

from gdrive_dl.exceptions import (
    AuthError,
    ChecksumError,
    ConfigError,
    DownloadError,
    FilterCostError,
    GdriveError,
    ManifestError,
    RateLimitError,
    SourceNotFoundError,
)


class TestExceptionHierarchy:
    """All custom exceptions inherit from GdriveError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthError,
            SourceNotFoundError,
            DownloadError,
            ChecksumError,
            RateLimitError,
            FilterCostError,
            ManifestError,
            ConfigError,
        ],
    )
    def test_all_exceptions_inherit_from_gdrive_error(self, exc_class):
        assert issubclass(exc_class, GdriveError)

    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthError,
            SourceNotFoundError,
            DownloadError,
            ChecksumError,
            RateLimitError,
            FilterCostError,
            ManifestError,
            ConfigError,
        ],
    )
    def test_all_exceptions_inherit_from_exception(self, exc_class):
        assert issubclass(exc_class, Exception)

    def test_gdrive_error_is_base(self):
        error = GdriveError("base error")
        assert isinstance(error, Exception)
        assert str(error) == "base error"


class TestDownloadError:
    """DownloadError captures file_id, name, and reason."""

    def test_stores_file_context(self):
        error = DownloadError(
            file_id="abc123",
            name="report.pdf",
            reason="403 Forbidden",
        )
        assert error.file_id == "abc123"
        assert error.name == "report.pdf"
        assert error.reason == "403 Forbidden"

    def test_str_includes_all_fields(self):
        error = DownloadError(
            file_id="abc123",
            name="report.pdf",
            reason="403 Forbidden",
        )
        message = str(error)
        assert "abc123" in message
        assert "report.pdf" in message
        assert "403 Forbidden" in message

    def test_is_gdrive_error(self):
        error = DownloadError(file_id="x", name="y", reason="z")
        assert isinstance(error, GdriveError)


class TestChecksumError:
    """ChecksumError captures file context and expected/actual checksums."""

    def test_stores_file_context(self):
        error = ChecksumError(
            file_id="abc123",
            name="report.pdf",
            expected="aaa",
            actual="bbb",
        )
        assert error.file_id == "abc123"
        assert error.name == "report.pdf"
        assert error.expected == "aaa"
        assert error.actual == "bbb"

    def test_str_includes_context(self):
        error = ChecksumError(
            file_id="abc123",
            name="report.pdf",
            expected="aaa",
            actual="bbb",
        )
        message = str(error)
        assert "report.pdf" in message
        assert "aaa" in message
        assert "bbb" in message


class TestSimpleExceptions:
    """Exceptions that take only a message string."""

    @pytest.mark.parametrize(
        "exc_class,message",
        [
            (AuthError, "OAuth token expired"),
            (SourceNotFoundError, "Folder not found: abc123"),
            (RateLimitError, "Rate limit exceeded"),
            (FilterCostError, "Filter requires 500 API calls"),
            (ManifestError, "Manifest file corrupted"),
            (ConfigError, "Invalid YAML config"),
        ],
    )
    def test_message_preserved(self, exc_class, message):
        error = exc_class(message)
        assert str(error) == message

    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthError,
            SourceNotFoundError,
            RateLimitError,
            FilterCostError,
            ManifestError,
            ConfigError,
        ],
    )
    def test_catchable_as_gdrive_error(self, exc_class):
        with pytest.raises(GdriveError):
            raise exc_class("test")
