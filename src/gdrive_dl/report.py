"""Report generation: dry-run preview and post-download reports."""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.table import Table

from gdrive_dl.constants import NON_DOWNLOADABLE

if TYPE_CHECKING:
    from gdrive_dl.manifest import Manifest
    from gdrive_dl.runner import SessionResult
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


# ---------------------------------------------------------------------------
# Post-download ReportGenerator
# ---------------------------------------------------------------------------

_FORMAT_EXTENSIONS: dict[str, str] = {
    "markdown": ".md",
    "html": ".html",
    "json": ".json",
}


class ReportGenerator:
    """Generate post-download reports in Markdown, HTML, or JSON."""

    def __init__(
        self,
        result: SessionResult,
        items: list[DriveItem],
        manifest: Manifest,
        folder_name: str,
        folder_id: str,
        output_dir: Path,
    ) -> None:
        self._result = result
        self._items = items
        self._manifest = manifest
        self._folder_name = folder_name
        self._folder_id = folder_id
        self._output_dir = output_dir

    def generate(self, fmt: str = "markdown") -> str:
        """Generate report in the specified format."""
        if fmt == "html":
            return self._generate_html()
        if fmt == "json":
            return self._generate_json()
        return self._generate_markdown()

    def save(self, fmt: str = "markdown") -> Path:
        """Write report to file and return the path."""
        ext = _FORMAT_EXTENSIONS.get(fmt, ".md")
        path = self._output_dir / f"gdrive-dl-report{ext}"
        content = self.generate(fmt)
        path.write_text(content, encoding="utf-8")
        return path

    # -- Data helpers -------------------------------------------------------

    def _session_data(self) -> dict[str, Any]:
        """Session metadata."""
        duration = ""
        duration_seconds = 0
        if self._result.start_time and self._result.end_time:
            try:
                start = datetime.fromisoformat(self._result.start_time)
                end = datetime.fromisoformat(self._result.end_time)
                delta = end - start
                duration_seconds = int(delta.total_seconds())
                minutes, secs = divmod(duration_seconds, 60)
                if minutes > 0:
                    duration = f"{minutes}m {secs}s"
                else:
                    duration = f"{secs}s"
            except (ValueError, TypeError):
                pass

        return {
            "start_time": self._result.start_time,
            "end_time": self._result.end_time,
            "duration": duration,
            "duration_seconds": duration_seconds,
            "source_name": self._folder_name,
            "source_id": self._folder_id,
            "output_dir": str(self._output_dir),
        }

    def _result_summary(self) -> dict[str, Any]:
        """Result counts."""
        total = (
            self._result.files_completed
            + self._result.files_failed
            + self._result.files_skipped
        )
        return {
            "completed": self._result.files_completed,
            "failed": self._result.files_failed,
            "skipped": self._result.files_skipped,
            "total": total,
            "bytes_downloaded": self._result.bytes_downloaded,
            "directories_created": self._result.directories_created,
        }

    def _failed_files(self) -> list[dict[str, str]]:
        """Files that failed download."""
        failed = []
        for entry in self._manifest.files.values():
            status = entry.get("status", "")
            if status in ("failed", "checksum_failed"):
                failed.append({
                    "name": entry.get("name", ""),
                    "path": entry.get("drivePath", ""),
                    "error": entry.get("error", "unknown"),
                })
        return failed

    def _skipped_files(self) -> list[dict[str, str]]:
        """Files that were skipped."""
        skipped = []
        for entry in self._manifest.files.values():
            if entry.get("status") == "skipped":
                skipped.append({
                    "name": entry.get("name", ""),
                    "path": entry.get("drivePath", ""),
                    "reason": entry.get("reason", "unknown"),
                })
        return skipped

    def _type_breakdown(self) -> list[tuple[str, int, int]]:
        """Group non-folder items by MIME type → (mime, count, size)."""
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

    # -- Markdown -----------------------------------------------------------

    def _generate_markdown(self) -> str:
        """Generate Markdown report."""
        session = self._session_data()
        results = self._result_summary()
        failed = self._failed_files()
        skipped = self._skipped_files()
        breakdown = self._type_breakdown()

        lines: list[str] = []
        lines.append("# gdrive-dl Download Report\n")

        # Session
        lines.append("## Session\n")
        lines.append(f"- **Source:** {session['source_name']} ({session['source_id']})")
        lines.append(f"- **Started:** {session['start_time']}")
        lines.append(f"- **Completed:** {session['end_time']}")
        lines.append(f"- **Duration:** {session['duration']}")
        lines.append(f"- **Output:** {session['output_dir']}")
        lines.append("")

        # Results
        lines.append("## Results\n")
        lines.append("| Status | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Completed | {results['completed']} |")
        lines.append(f"| Skipped | {results['skipped']} |")
        lines.append(f"| Failed | {results['failed']} |")
        lines.append(f"| **Total** | **{results['total']}** |")
        lines.append("")
        lines.append(f"**Bytes Downloaded:** {format_bytes(results['bytes_downloaded'])}")
        lines.append(f"**Directories:** {results['directories_created']}")
        lines.append("")

        # Type breakdown
        if breakdown:
            lines.append("## Type Breakdown\n")
            lines.append("| MIME Type | Count | Size |")
            lines.append("|-----------|-------|------|")
            for mime, count, size in breakdown:
                lines.append(f"| {mime} | {count} | {format_bytes(size)} |")
            lines.append("")

        # Failed files
        if failed:
            lines.append("## Failed Files\n")
            lines.append("| File | Path | Error |")
            lines.append("|------|------|-------|")
            for f in failed:
                lines.append(f"| {f['name']} | {f['path']} | {f['error']} |")
            lines.append("")

        # Skipped files
        if skipped:
            lines.append("## Skipped Files\n")
            lines.append("| File | Path | Reason |")
            lines.append("|------|------|--------|")
            for s in skipped:
                lines.append(f"| {s['name']} | {s['path']} | {s['reason']} |")
            lines.append("")

        return "\n".join(lines)

    # -- HTML ---------------------------------------------------------------

    def _generate_html(self) -> str:
        """Generate self-contained HTML report."""
        session = self._session_data()
        results = self._result_summary()
        failed = self._failed_files()
        skipped = self._skipped_files()
        breakdown = self._type_breakdown()

        parts: list[str] = []
        parts.append("<!DOCTYPE html>")
        parts.append("<html><head><meta charset='utf-8'>")
        parts.append("<title>gdrive-dl Download Report</title>")
        parts.append("<style>")
        parts.append("body { font-family: sans-serif; max-width: 900px; "
                     "margin: 2em auto; padding: 0 1em; }")
        parts.append("table { border-collapse: collapse; width: 100%; "
                     "margin: 1em 0; }")
        parts.append("th, td { border: 1px solid #ddd; padding: 8px; "
                     "text-align: left; }")
        parts.append("th { background: #f5f5f5; }")
        parts.append("h1, h2 { color: #333; }")
        parts.append("</style></head><body>")

        parts.append("<h1>gdrive-dl Download Report</h1>")

        # Session
        parts.append("<h2>Session</h2><ul>")
        parts.append(f"<li><b>Source:</b> {session['source_name']} "
                     f"({session['source_id']})</li>")
        parts.append(f"<li><b>Started:</b> {session['start_time']}</li>")
        parts.append(f"<li><b>Completed:</b> {session['end_time']}</li>")
        parts.append(f"<li><b>Duration:</b> {session['duration']}</li>")
        parts.append(f"<li><b>Output:</b> {session['output_dir']}</li>")
        parts.append("</ul>")

        # Results
        parts.append("<h2>Results</h2><table>")
        parts.append("<tr><th>Status</th><th>Count</th></tr>")
        parts.append(f"<tr><td>Completed</td><td>{results['completed']}</td></tr>")
        parts.append(f"<tr><td>Skipped</td><td>{results['skipped']}</td></tr>")
        parts.append(f"<tr><td>Failed</td><td>{results['failed']}</td></tr>")
        parts.append(f"<tr><td><b>Total</b></td>"
                     f"<td><b>{results['total']}</b></td></tr>")
        parts.append("</table>")
        parts.append(f"<p><b>Bytes Downloaded:</b> "
                     f"{format_bytes(results['bytes_downloaded'])}</p>")

        # Type breakdown
        if breakdown:
            parts.append("<h2>Type Breakdown</h2><table>")
            parts.append("<tr><th>MIME Type</th><th>Count</th><th>Size</th></tr>")
            for mime, count, size in breakdown:
                parts.append(f"<tr><td>{mime}</td><td>{count}</td>"
                             f"<td>{format_bytes(size)}</td></tr>")
            parts.append("</table>")

        # Failed files
        if failed:
            parts.append("<h2>Failed Files</h2><table>")
            parts.append("<tr><th>File</th><th>Path</th><th>Error</th></tr>")
            for f in failed:
                parts.append(f"<tr><td>{f['name']}</td><td>{f['path']}</td>"
                             f"<td>{f['error']}</td></tr>")
            parts.append("</table>")

        # Skipped files
        if skipped:
            parts.append("<h2>Skipped Files</h2><table>")
            parts.append("<tr><th>File</th><th>Path</th><th>Reason</th></tr>")
            for s in skipped:
                parts.append(f"<tr><td>{s['name']}</td><td>{s['path']}</td>"
                             f"<td>{s['reason']}</td></tr>")
            parts.append("</table>")

        parts.append("</body></html>")
        return "\n".join(parts)

    # -- JSON ---------------------------------------------------------------

    def _generate_json(self) -> str:
        """Generate JSON report."""
        session = self._session_data()
        results = self._result_summary()
        breakdown = self._type_breakdown()

        data: dict[str, Any] = {
            "session": {
                "started": session["start_time"],
                "completed": session["end_time"],
                "duration_seconds": session["duration_seconds"],
                "source": {
                    "name": session["source_name"],
                    "id": session["source_id"],
                },
                "output_dir": session["output_dir"],
            },
            "results": {
                "completed": results["completed"],
                "skipped": results["skipped"],
                "failed": results["failed"],
                "total": results["total"],
                "bytes_downloaded": results["bytes_downloaded"],
                "directories_created": results["directories_created"],
            },
            "type_breakdown": {
                mime: {"count": count, "bytes": size}
                for mime, count, size in breakdown
            },
            "failed_files": self._failed_files(),
            "skipped_files": self._skipped_files(),
        }

        return json.dumps(data, indent=2, ensure_ascii=False)
