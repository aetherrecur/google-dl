"""DownloadRunner — orchestrates walk → download → checksum → timestamp → manifest."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from gdrive_dl import checksums, downloader, filters, timestamps, walker
from gdrive_dl.manifest import DownloadStatus, Manifest
from gdrive_dl.report import DryRunReporter
from gdrive_dl.throttle import TokenBucketThrottler

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    """Aggregate outcome of a download session."""

    files_completed: int = 0
    files_failed: int = 0
    files_skipped: int = 0
    bytes_downloaded: int = 0
    directories_created: int = 0


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

        if rate_limit is not None:
            self._throttler = TokenBucketThrottler(
                rate=rate_limit, fixed=True,
            )
        else:
            self._throttler = TokenBucketThrottler()

    def run(self, root_folder_id: str) -> SessionResult:
        """Execute the full download pipeline."""
        result = SessionResult()

        # Walk the folder tree
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

        # Set up progress tracking
        task_id = None
        if self._progress is not None:
            task_id = self._progress.add_task(
                "Downloading", total=len(files),
            )

        # Download files
        for item in files:
            # Skip already completed
            if self._manifest.is_completed(item.id):
                logger.debug("Skipping already completed: %s", item.name)
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
                throttler=self._throttler,
            )

            # Process result
            if dl_result.status == DownloadStatus.COMPLETED:
                # Verify checksum
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
                )
                result.files_completed += 1
                result.bytes_downloaded += dl_result.bytes_downloaded

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

        return result


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
