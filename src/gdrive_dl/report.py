"""Dry-run report generation with Rich formatted output."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from rich.console import Console
from rich.table import Table

from gdrive_dl.constants import NON_DOWNLOADABLE

if TYPE_CHECKING:
    from gdrive_dl.walker import DriveItem

logger = logging.getLogger(__name__)


def format_bytes(n: int) -> str:
    """Format byte count as human-readable string."""
    if n < 1_000:
        return f"{n} B"
    if n < 1_000_000:
        return f"{n / 1_000:.1f} KB"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.1f} MB"
    return f"{n / 1_000_000_000:.1f} GB"


class DryRunReporter:
    """Generate a dry-run report from a list of DriveItems."""

    def __init__(
        self,
        items: list[DriveItem],
        folder_name: str,
        folder_id: str,
    ) -> None:
        self._items = items
        self._folder_name = folder_name
        self._folder_id = folder_id

    def _count_stats(self) -> dict[str, int]:
        """Compute aggregate counts from items."""
        dir_count = 0
        file_count = 0
        workspace_count = 0
        non_downloadable_count = 0
        total_size = 0

        for item in self._items:
            if item.is_folder:
                dir_count += 1
                continue

            if item.mime_type in NON_DOWNLOADABLE:
                non_downloadable_count += 1
                continue

            file_count += 1
            if item.is_workspace_file:
                workspace_count += 1
            elif item.size is not None:
                total_size += item.size

        return {
            "dir_count": dir_count,
            "file_count": file_count,
            "workspace_count": workspace_count,
            "non_downloadable_count": non_downloadable_count,
            "total_size": total_size,
        }

    def _type_breakdown(self) -> list[tuple[str, int, int]]:
        """Group files by MIME type → (mime, count, total_size), sorted by count desc."""
        counts: dict[str, int] = {}
        sizes: dict[str, int] = {}

        for item in self._items:
            if item.is_folder or (item.mime_type in NON_DOWNLOADABLE):
                continue
            counts[item.mime_type] = counts.get(item.mime_type, 0) + 1
            sizes[item.mime_type] = sizes.get(item.mime_type, 0) + (item.size or 0)

        return sorted(
            [(mime, counts[mime], sizes[mime]) for mime in counts],
            key=lambda x: x[1],
            reverse=True,
        )

    def _non_downloadable_list(self) -> list[tuple[str, str]]:
        """List non-downloadable items as (drive_path, mime_type)."""
        return [
            (item.drive_path, item.mime_type)
            for item in self._items
            if (not item.is_folder) and (item.mime_type in NON_DOWNLOADABLE)
        ]

    def generate(self) -> str:
        """Generate and display the dry-run report. Returns plain-text summary."""
        stats = self._count_stats()
        breakdown = self._type_breakdown()
        non_downloadable = self._non_downloadable_list()

        buf = io.StringIO()
        console = Console(file=buf, force_terminal=False, width=100)

        console.print()
        console.print("[bold]gdrive-dl dry run report[/bold]")
        console.print("=" * 40)
        console.print()
        console.print(f"Source:            {self._folder_name} ({self._folder_id})")
        console.print(f"Directories:       {stats['dir_count']}")

        blob_count = stats["file_count"] - stats["workspace_count"]
        console.print(
            f"Downloadable:      {blob_count} files "
            f"({format_bytes(stats['total_size'])} estimated)"
        )
        if stats["workspace_count"] > 0:
            console.print(
                f"Workspace files:   {stats['workspace_count']} files "
                f"(exported size unknown until download)"
            )
        if stats["non_downloadable_count"] > 0:
            console.print(
                f"Non-downloadable:  {stats['non_downloadable_count']} items"
            )

        # API call estimate
        download_calls = stats["file_count"]
        console.print()
        console.print(
            f"Estimated API calls: ~{download_calls} downloads"
        )

        # Type breakdown
        if breakdown:
            console.print()
            table = Table(title="Files by type")
            table.add_column("MIME Type", style="cyan")
            table.add_column("Count", justify="right")
            table.add_column("Size", justify="right")
            for mime, count, size in breakdown:
                table.add_row(mime, str(count), format_bytes(size))
            console.print(table)

        # Non-downloadable items
        if non_downloadable:
            console.print()
            table = Table(title="Non-downloadable items")
            table.add_column("Path", style="yellow")
            table.add_column("MIME Type")
            for path, mime in non_downloadable:
                table.add_row(path, mime)
            console.print(table)

        console.print()

        return buf.getvalue()
