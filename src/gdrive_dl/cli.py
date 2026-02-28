"""CLI entry point for gdrive-dl."""

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
from gdrive_dl.exceptions import AuthError, GdriveError, SourceNotFoundError
from gdrive_dl.manifest import Manifest
from gdrive_dl.runner import DownloadRunner, create_progress


@click.command()
@click.version_option(version=__version__, prog_name="gdrive-dl")
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
def main(
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
    rate_limit: Optional[float],
    retries: int,
) -> None:
    """gdrive-dl: Google Drive archival CLI.

    SOURCE is a Google Drive folder URL, folder ID, or 'root' for My Drive.
    """
    try:
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

        # 8. Run download
        click.echo(f"Downloading to: {output_dir}/")
        progress = create_progress()

        with progress:
            runner = DownloadRunner(
                service=service,
                output_dir=output_dir,
                manifest=manifest,
                creds=creds,
                progress=progress,
                rate_limit=rate_limit,
                max_retries=retries,
                api_query=query,
                post_filter=post_filter,
                filter_confirm=filter_confirm,
            )
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

    except (AuthError, SourceNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc
    except GdriveError as exc:
        raise click.ClickException(str(exc)) from exc
