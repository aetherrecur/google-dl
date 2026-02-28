"""MD5 checksum verification for downloaded files."""

import hashlib
from pathlib import Path
from typing import Optional

from gdrive_dl.exceptions import ChecksumError

_BUFFER_SIZE = 65536  # 64 KB read buffer


def verify_checksum(
    file_path: Path,
    expected_md5: Optional[str],
    file_id: str = "",
    name: str = "",
) -> bool:
    """Verify MD5 checksum of a downloaded file.

    Returns True if checksum matches or no expected checksum was provided
    (Workspace exports have no md5Checksum in the Drive API response).

    Raises:
        ChecksumError: On mismatch (caller decides retry policy).
    """
    if expected_md5 is None:
        return True

    md5 = hashlib.md5()
    with file_path.open("rb") as f:
        while True:
            chunk = f.read(_BUFFER_SIZE)
            if not chunk:
                break
            md5.update(chunk)

    actual = md5.hexdigest()
    if actual != expected_md5:
        raise ChecksumError(
            file_id=file_id,
            name=name,
            expected=expected_md5,
            actual=actual,
        )
    return True
