"""CLI entry point for gdrive-dl."""

import signal
import sys
from pathlib import Path
from typing import Optional

import click

from gdrive_dl import __version__
from gdrive_dl.auth import (
    build_drive_service,
    extract_folder_id,
    format_drive_about,
    get_drive_about,
    verify_source_folder,
)
from gdrive_dl.config import build_export_config, load_config_callback
from gdrive_dl.exceptions import AuthError, ConfigError, GdriveError, SourceNotFoundError
from gdrive_dl.manifest import Manifest
from gdrive_dl.report import ReportGenerator
from gdrive_dl.runner import DownloadRunner, create_progress
from gdrive_dl.walker import list_shared_drives


def select_shared_drives(service: object) -> list[dict[str, str]]:
    """Interactive selection of Shared Drives.

    Enumerates accessible drives, displays a numbered list,
    and prompts the user for a selection.
    """
    drives = list_shared_drives(service)
    if not drives:
        click.echo("No Shared Drives accessible.")
        return []

    click.echo("Accessible Shared Drives:")
    for i, drive in enumerate(drives, 1):
        click.echo(f"  {i}. {drive['name']}")

    selection = click.prompt(
        "Select drives (comma-separated numbers, or 'all')",
        type=str,
    )

    if selection.strip().lower() == "all":
        return drives

    selected: list[dict[str, str]] = []
    for part in selection.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(drives):
                selected.append(drives[idx])
    return selected


@click.command()
@click.version_option(version=__version__, prog_name="gdrive-dl")
@click.option(
    "--config",
    callback=load_config_callback,
    is_eager=True,
    expose_value=False,
    help="YAML config file path. Auto-discovered if not provided.",
)
@click.argument("source")
@click.option(
    "--credentials",
    default="./credentials.json",
    show_default=True,
    help="Path to OAuth credentials JSON.",
)
@click.option(
    "--token",
    default="./token.json",
    show_default=True,
    help="Path to cached token file.",
)
@click.option(
    "--service-account",
    default=None,
    help="Use a service account key file instead of OAuth.",
)
@click.option(
    "--browser",
    default=None,
    help="Browser for OAuth sign-in (e.g., chrome, firefox, auto).",
)
@click.option(
    "--no-browser",
    is_flag=True,
    default=False,
    help="Print authorization URL instead of opening a browser.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Output directory (default: ./<folder_name>/).",
)
@click.option(
    "--query",
    default=None,
    help="API-level filter (Google Drive query syntax, injected into 'q' parameter).",
)
@click.option(
    "--filter",
    "post_filter",
    default=None,
    help="Post-fetch filter expression (e.g., 'size>10mb,ext:.pdf,name:report').",
)
@click.option(
    "--filter-confirm",
    is_flag=True,
    default=False,
    help="Allow expensive filter operations (>100 API calls).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be downloaded without downloading.",
)
@click.option(
    "--rate-limit",
    type=float,
    default=None,
    help="Fixed API rate limit (requests/sec). Disables adaptive throttle.",
)
@click.option(
    "--retries",
    type=int,
    default=5,
    show_default=True,
    help="Max retries per API call on transient errors.",
)
@click.option(
    "--permissions",
    is_flag=True,
    default=False,
    help="Save permissions manifest per file.",
)
@click.option(
    "--comments",
    is_flag=True,
    default=False,
    help="Export comments as sidecar files.",
)
@click.option(
    "--metadata",
    is_flag=True,
    default=False,
    help="Save Drive metadata as sidecar JSON.",
)
@click.option(
    "--revisions",
    type=int,
    is_flag=False,
    flag_value=0,
    default=None,
    help="Download revision history. No value=all, N=N most recent.",
)
@click.option(
    "--export-format",
    "export_format",
    multiple=True,
    help="Export format override: TYPE=FORMAT (e.g., docs=pdf). Repeatable.",
)
@click.option(
    "--report",
    is_flag=True,
    default=False,
    help="Generate download report after completion.",
)
@click.option(
    "--report-format",
    type=click.Choice(["markdown", "html", "json"]),
    default="markdown",
    show_default=True,
    help="Report output format.",
)
@click.option(
    "--shared-drives",
    default=None,
    help="Include Shared Drives. Use '=list' to select interactively.",
)
@click.option(
    "--no-verify",
    is_flag=True,
    default=False,
    help="Skip MD5 checksum verification after download.",
)
@click.option(
    "--shared-with-me",
    is_flag=True,
    default=False,
    help="Query the 'Shared with me' collection instead of walking a folder tree.",
)
@click.pass_context
def main(
    ctx: click.Context,
    source: str,
    credentials: str,
    token: str,
    service_account: Optional[str],
    browser: Optional[str],
    no_browser: bool,
    output: Optional[str],
    query: Optional[str],
    post_filter: Optional[str],
    filter_confirm: bool,
    dry_run: bool,
    rate_limit: Optional[float],
    retries: int,
    permissions: bool,
    comments: bool,
    metadata: bool,
    revisions: Optional[int],
    export_format: tuple[str, ...],
    report: bool,
    report_format: str,
    shared_drives: Optional[str],
    no_verify: bool,
    shared_with_me: bool,
) -> None:
    """gdrive-dl: Google Drive archival CLI.

    SOURCE is a Google Drive folder URL, folder ID, or 'root' for My Drive.
    """
    try:
        # 0. Build export config from YAML + CLI overrides
        raw_export = ctx.meta.get("raw_config", {}).get("export_formats")
        export_config = build_export_config(raw_export, export_format)

        # 1. Extract folder ID from source
        folder_id = extract_folder_id(source)

        # 2. Authenticate and build Drive service
        click.echo("Authenticating...")
        service = build_drive_service(
            credentials_file=credentials,
            token_file=token,
            service_account_file=service_account,
            browser=browser,
            no_browser=no_browser,
        )

        # 3. Post-auth smoke test: display Drive metadata
        about = get_drive_about(service)
        click.echo(format_drive_about(about))
        click.echo()

        # 4. Verify source folder exists
        folder_meta = verify_source_folder(service, folder_id)
        folder_name = folder_meta.get("name", folder_id)
        click.echo(f"Source folder: {folder_name} ({folder_id})")
        click.echo()

        # 5. Determine output directory
        output_dir = Path(output) if output else Path(f"./{folder_name}")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 6. Set up manifest
        manifest_path = output_dir / "gdrive-dl-manifest.json"
        manifest = Manifest.load_or_create(str(manifest_path))

        # 7. Get credentials for exportLinks fallback
        creds = None
        if not service_account:
            # For OAuth, we can access the credentials from the service
            try:
                creds = service._http.credentials
            except AttributeError:
                pass

        # 8. Run download (or dry-run)
        runner_kwargs = {
            "service": service,
            "output_dir": output_dir,
            "manifest": manifest,
            "creds": creds,
            "rate_limit": rate_limit,
            "max_retries": retries,
            "api_query": query,
            "post_filter": post_filter,
            "filter_confirm": filter_confirm,
            "dry_run": dry_run,
            "folder_name": folder_name,
            "folder_id": folder_id,
            "permissions": permissions,
            "comments": comments,
            "metadata": metadata,
            "revisions": revisions,
            "export_config": export_config,
            "no_verify": no_verify,
            "shared_with_me": shared_with_me,
        }

        # Set up signal handlers for graceful shutdown
        def _signal_handler(signum: int, _frame: object) -> None:
            manifest.save()
            sys.exit(128 + signum)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        if dry_run:
            runner = DownloadRunner(**runner_kwargs)
            runner.run(folder_id)
        else:
            click.echo(f"Downloading to: {output_dir}/")
            progress = create_progress()

            with progress:
                runner = DownloadRunner(progress=progress, **runner_kwargs)
                result = runner.run(folder_id)

            # 9. Summary
            click.echo()
            click.echo("Download complete!")
            click.echo(f"  Files downloaded: {result.files_completed}")
            if result.files_failed > 0:
                click.echo(f"  Files failed:     {result.files_failed}")
            if result.files_skipped > 0:
                click.echo(f"  Files skipped:    {result.files_skipped}")
            click.echo(f"  Directories:      {result.directories_created}")
            click.echo(f"  Total bytes:      {result.bytes_downloaded:,}")

            # 10. Generate report if requested
            if report:
                report_gen = ReportGenerator(
                    result=result,
                    items=runner.last_items,
                    manifest=manifest,
                    folder_name=folder_name,
                    folder_id=folder_id,
                    output_dir=output_dir,
                )
                report_path = report_gen.save(report_format)
                click.echo(f"  Report saved:     {report_path}")

            # 11. Exit code 1 on partial failure
            if result.files_failed > 0:
                ctx.exit(1)

    except (AuthError, SourceNotFoundError, ConfigError) as exc:
        raise click.ClickException(str(exc)) from exc
    except GdriveError as exc:
        raise click.ClickException(str(exc)) from exc
