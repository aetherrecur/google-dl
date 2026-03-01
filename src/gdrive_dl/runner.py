"""DownloadRunner — orchestrates walk → download → checksum → timestamp → manifest."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from gdrive_dl import archival, checksums, downloader, filters, timestamps, walker
from gdrive_dl.manifest import DownloadStatus, Manifest
from gdrive_dl.report import DryRunReporter
from gdrive_dl.throttle import TokenBucketThrottler

if TYPE_CHECKING:
    from gdrive_dl.config import ExportConfig

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    """Aggregate outcome of a download session."""

    files_completed: int = 0
    files_failed: int = 0
    files_skipped: int = 0
    bytes_downloaded: int = 0
    directories_created: int = 0
    start_time: str = ""
    end_time: str = ""


class DownloadRunner:
    """Coordinates the full download pipeline.

    walk → download → checksum → timestamp → manifest for each file.
    """

    def __init__(
        self,
        service: Any,
        output_dir: Path,
        manifest: Manifest,
        creds: Any | None = None,
        progress: Progress | None = None,
        rate_limit: float | None = None,
        max_retries: int = 5,
        api_query: str | None = None,
        post_filter: str | None = None,
        filter_confirm: bool = False,
        dry_run: bool = False,
        folder_name: str = "",
        folder_id: str = "",
        permissions: bool = False,
        comments: bool = False,
        metadata: bool = False,
        revisions: int | None = None,
        export_config: ExportConfig | None = None,
        no_verify: bool = False,
    ) -> None:
        self._service = service
        self._output_dir = output_dir
        self._manifest = manifest
        self._creds = creds
        self._progress = progress
        self._max_retries = max_retries
        self._api_query = api_query
        self._post_filter = post_filter
        self._filter_confirm = filter_confirm
        self._dry_run = dry_run
        self._folder_name = folder_name
        self._folder_id = folder_id
        self._permissions = permissions
        self._comments = comments
        self._metadata = metadata
        self._revisions = revisions
        self._export_config = export_config
        self._no_verify = no_verify

        if rate_limit is not None:
            self._throttler = TokenBucketThrottler(
                rate=rate_limit, fixed=True,
            )
        else:
            self._throttler = TokenBucketThrottler()

    def run(self, root_folder_id: str) -> SessionResult:
        """Execute the full download pipeline."""
        result = SessionResult()
        result.start_time = datetime.now(timezone.utc).isoformat()

        # Walk the folder tree
        self._last_items: list[walker.DriveItem] = []
        items = walker.walk(
            self._service, root_folder_id,
            throttler=self._throttler,
            extra_query=self._api_query,
        )
        logger.info("Found %d items to process", len(items))

        # Apply post-fetch filter
        if self._post_filter:
            items = filters.apply_post_filter(
                items, self._post_filter, filter_confirm=self._filter_confirm,
            )
            logger.info("After filtering: %d items", len(items))

        # Store items for post-download reporting
        self._last_items = items

        # Dry-run: generate report and return without downloading
        if self._dry_run:
            reporter = DryRunReporter(
                items, self._folder_name, self._folder_id,
            )
            report_text = reporter.generate()
            from rich.console import Console
            Console().print(report_text, highlight=False)
            return result

        # Separate folders and files
        folders = [i for i in items if i.is_folder]
        files = [i for i in items if not i.is_folder]

        # Create directories first
        for folder_item in folders:
            dir_path = self._output_dir / folder_item.drive_path
            dir_path.mkdir(parents=True, exist_ok=True)
            result.directories_created += 1
            self._run_archival(folder_item)

        # Set up progress tracking
        task_id = None
        if self._progress is not None:
            task_id = self._progress.add_task(
                "Downloading", total=len(files),
            )

        # Download files
        for item in files:
            # Skip already completed and unchanged
            if self._manifest.is_completed_and_unchanged(item.id, item.modified_time):
                logger.debug("Skipping completed and unchanged: %s", item.name)
                if (self._progress is not None) and (task_id is not None):
                    self._progress.advance(task_id)
                continue

            self._manifest.update_file(
                item.id, DownloadStatus.IN_PROGRESS, name=item.name,
                drivePath=item.drive_path,
            )

            # Determine local path
            local_path = self._output_dir / item.drive_path

            # Download
            dl_result = downloader.download_file(
                self._service, item, local_path,
                creds=self._creds,
                export_links=item.export_links,
                throttler=self._throttler,
                export_config=self._export_config,
            )

            # Process result
            if dl_result.status == DownloadStatus.COMPLETED:
                # Verify checksum (unless --no-verify)
                if not self._no_verify:
                    try:
                        checksums.verify_checksum(
                            local_path,
                            item.md5_checksum,
                            file_id=item.id,
                            name=item.name,
                        )
                    except Exception as exc:
                        logger.warning("Checksum failed for %s: %s", item.name, exc)
                        self._manifest.update_file(
                            item.id, DownloadStatus.CHECKSUM_FAILED,
                            error=str(exc),
                        )
                        result.files_failed += 1
                        if (self._progress is not None) and (task_id is not None):
                            self._progress.advance(task_id)
                        continue

                # Apply timestamps
                try:
                    timestamps.apply_timestamps(
                        local_path,
                        modified_time=item.modified_time,
                        created_time=item.created_time or None,
                    )
                except Exception as exc:
                    logger.warning("Timestamp failed for %s: %s", item.name, exc)

                self._manifest.update_file(
                    item.id, DownloadStatus.COMPLETED,
                    localPath=str(local_path),
                    bytesDownloaded=dl_result.bytes_downloaded,
                    modifiedTime=item.modified_time,
                )
                result.files_completed += 1
                result.bytes_downloaded += dl_result.bytes_downloaded
                self._run_archival(item)

            elif dl_result.status == DownloadStatus.SKIPPED:
                self._manifest.update_file(
                    item.id, DownloadStatus.SKIPPED,
                    reason=dl_result.error_message,
                )
                result.files_skipped += 1

            else:  # FAILED
                self._manifest.update_file(
                    item.id, DownloadStatus.FAILED,
                    error=dl_result.error_message,
                )
                result.files_failed += 1

            if (self._progress is not None) and (task_id is not None):
                self._progress.advance(task_id)

        # Apply directory timestamps bottom-up (deepest first)
        sorted_folders = sorted(
            folders, key=lambda f: f.drive_path.count("/"), reverse=True,
        )
        for folder_item in sorted_folders:
            dir_path = self._output_dir / folder_item.drive_path
            if dir_path.exists():
                try:
                    timestamps.apply_timestamps(
                        dir_path,
                        modified_time=folder_item.modified_time,
                        created_time=folder_item.created_time or None,
                    )
                except Exception as exc:
                    logger.warning(
                        "Directory timestamp failed for %s: %s",
                        folder_item.name, exc,
                    )

        # Final manifest flush
        self._manifest.save()

        result.end_time = datetime.now(timezone.utc).isoformat()
        return result

    @property
    def last_items(self) -> list[walker.DriveItem]:
        """Items from the most recent run (for post-download reporting)."""
        return self._last_items

    def _run_archival(self, item: walker.DriveItem) -> None:
        """Run enabled archival functions for a single item. Best-effort."""
        is_folder = item.is_folder

        if self._permissions:
            archival.save_permissions(
                self._service, item, self._output_dir, self._throttler,
            )

        if self._metadata:
            archival.save_metadata(item, self._output_dir)

        # Comments and revisions only for files, not folders
        if (not is_folder) and self._comments:
            archival.save_comments(
                self._service, item, self._output_dir, self._throttler,
            )

        if (not is_folder) and (self._revisions is not None):
            archival.save_revisions(
                self._service, item, self._output_dir, self._throttler,
                creds=self._creds, revision_count=self._revisions or None,
            )


def create_progress() -> Progress:
    """Create a Rich Progress instance for download tracking."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
    )
