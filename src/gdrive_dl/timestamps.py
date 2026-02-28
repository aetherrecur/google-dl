"""Apply Drive file timestamps to local files via os.utime()."""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def apply_timestamps(
    file_path: Path,
    modified_time: str,
    created_time: Optional[str] = None,
) -> None:
    """Set mtime and atime on a local file from Drive RFC 3339 timestamps.

    Args:
        file_path: Local file or directory path.
        modified_time: Drive modifiedTime (RFC 3339).
        created_time: Drive createdTime (RFC 3339), or None.

    mtime is set from modifiedTime. atime is set from createdTime if
    available, otherwise falls back to modifiedTime. Call after file is
    fully written and checksum-verified. For directories, call bottom-up
    (children before parents) to prevent child writes from updating parent mtime.
    """
    mtime = _parse_rfc3339(modified_time)
    atime = _parse_rfc3339(created_time) if created_time else mtime
    os.utime(file_path, (atime, mtime))


def _parse_rfc3339(timestamp: str) -> float:
    """Parse RFC 3339 timestamp string to POSIX float seconds.

    Handles Google's 'Z' suffix which datetime.fromisoformat() doesn't
    support in Python < 3.11.
    """
    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return dt.timestamp()
