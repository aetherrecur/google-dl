"""CLI entry point for gdrive-dl."""

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
def main(
    source: str,
    credentials: str,
    token: str,
    service_account: Optional[str],
    browser: Optional[str],
    no_browser: bool,
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
        click.echo("Phase 1 complete — auth and source verification working.")
        click.echo("Download functionality will be implemented in Phase 2.")

    except (AuthError, SourceNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc
    except GdriveError as exc:
        raise click.ClickException(str(exc)) from exc
