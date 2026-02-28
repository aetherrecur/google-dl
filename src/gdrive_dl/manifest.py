"""Manifest tracking for download sessions — read/write, resume, atomic flush."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from gdrive_dl.exceptions import ManifestError

SCHEMA_VERSION = 1
FLUSH_EVERY_N = 10
FLUSH_EVERY_S = 30.0


class DownloadStatus(str, Enum):
    """Status of a file in the download manifest."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CHECKSUM_FAILED = "checksum_failed"


class Manifest:
    """Tracks download status per file with atomic persistence.

    In-memory updates on every status change, with periodic auto-flush
    (every FLUSH_EVERY_N completions or FLUSH_EVERY_S seconds).
    Always flush on clean exit via save().
    """

    def __init__(self, path: Path, data: dict[str, Any]) -> None:
        self._path = path
        self._data = data
        self._dirty = False
        self._completions_since_flush = 0
        self._last_flush_time = time.monotonic()

    @classmethod
    def load_or_create(cls, path: str) -> Manifest:
        """Load an existing manifest or create a fresh one.

        Raises:
            ManifestError: If the file is corrupt or has incompatible schema.
        """
        manifest_path = Path(path)
        if manifest_path.exists():
            try:
                raw = json.loads(manifest_path.read_text())
            except json.JSONDecodeError as exc:
                raise ManifestError(f"Corrupt manifest file: {exc}") from exc
            version = raw.get("schemaVersion")
            if version is None:
                raise ManifestError("Missing schema version in manifest")
            if version != SCHEMA_VERSION:
                raise ManifestError(
                    f"Incompatible manifest schema v{version} "
                    f"(supported: v{SCHEMA_VERSION}). "
                    "Please upgrade gdrive-dl."
                )
            return cls(manifest_path, raw)

        data: dict[str, Any] = {
            "schemaVersion": SCHEMA_VERSION,
            "sessionId": str(uuid.uuid4()),
            "createdAt": _utcnow(),
            "updatedAt": _utcnow(),
            "files": {},
        }
        return cls(manifest_path, data)

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        """Return the manifest entry for file_id, or None if not tracked."""
        result: dict[str, Any] | None = self._data["files"].get(file_id)
        return result

    def is_completed(self, file_id: str) -> bool:
        """Return True if this file_id has COMPLETED status."""
        entry = self._data["files"].get(file_id)
        return (entry is not None) and (entry.get("status") == DownloadStatus.COMPLETED.value)

    def is_completed_and_unchanged(self, file_id: str, modified_time: str) -> bool:
        """Return True if file is COMPLETED and modifiedTime matches.

        Used for resume logic: skip re-downloading files that haven't changed.
        """
        entry = self._data["files"].get(file_id)
        if entry is None:
            return False
        if entry.get("status") != DownloadStatus.COMPLETED.value:
            return False
        return bool(entry.get("modifiedTime") == modified_time)

    def update_file(
        self,
        file_id: str,
        status: DownloadStatus,
        **kwargs: Any,
    ) -> None:
        """Update or create a file entry. Triggers auto-flush on threshold."""
        entry = self._data["files"].setdefault(file_id, {"fileId": file_id})
        entry["status"] = status.value
        entry.update(kwargs)
        self._data["updatedAt"] = _utcnow()
        self._dirty = True

        if status == DownloadStatus.COMPLETED:
            self._completions_since_flush += 1

        self._maybe_flush()

    def save(self) -> None:
        """Force-flush manifest to disk atomically."""
        if not self._dirty:
            return
        _atomic_write(self._path, self._data)
        self._dirty = False
        self._completions_since_flush = 0
        self._last_flush_time = time.monotonic()

    @property
    def files(self) -> dict[str, Any]:
        """Read-only access to the files dict."""
        result: dict[str, Any] = self._data["files"]
        return result

    def _maybe_flush(self) -> None:
        elapsed = time.monotonic() - self._last_flush_time
        if (
            (self._completions_since_flush >= FLUSH_EVERY_N)
            or (elapsed >= FLUSH_EVERY_S)
        ):
            self.save()


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically using mkstemp + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _utcnow() -> str:
    """Return current UTC time as RFC 3339 string."""
    return datetime.now(timezone.utc).isoformat()
