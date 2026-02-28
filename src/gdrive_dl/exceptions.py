"""Custom exception hierarchy for gdrive-dl.

All exceptions inherit from GdriveError, enabling callers to catch
the full hierarchy with a single except clause when appropriate.
"""


class GdriveError(Exception):
    """Base exception for all gdrive-dl errors."""


class AuthError(GdriveError):
    """Authentication or authorization failure (fatal)."""


class SourceNotFoundError(GdriveError):
    """Requested Drive folder/file does not exist or is inaccessible (fatal)."""


class DownloadError(GdriveError):
    """Per-file download failure (non-fatal — logged to manifest, continues)."""

    def __init__(self, file_id: str, name: str, reason: str) -> None:
        self.file_id = file_id
        self.name = name
        self.reason = reason
        super().__init__(f"Failed to download '{name}' ({file_id}): {reason}")


class ChecksumError(GdriveError):
    """Checksum verification failure after download (non-fatal)."""

    def __init__(self, file_id: str, name: str, expected: str, actual: str) -> None:
        self.file_id = file_id
        self.name = name
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Checksum mismatch for '{name}' ({file_id}): "
            f"expected {expected}, got {actual}"
        )


class RateLimitError(GdriveError):
    """API rate limit exceeded (retried internally by throttle.py)."""


class FilterCostError(GdriveError):
    """Post-fetch filter would trigger too many API calls without confirmation."""


class ManifestError(GdriveError):
    """Manifest file is corrupt, missing, or has incompatible schema."""


class ConfigError(GdriveError):
    """Invalid configuration (YAML parse error, missing file, bad values)."""
