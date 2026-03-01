"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            commands.py
@TestClass       test_commands.py
@Purpose         Click CLI command layer for the Headshot Upload tool. Parses arguments, calls module
                 functions, and formats console output. Contains NO business logic — delegates entirely
                 to the modules layer.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional

import click
from dotenv import load_dotenv

from headshot_upload import __version__

__author__ = "Marimuthu V S"

# ─── Constants ─────────────────────────────────────────────────────────────────────────────────────────────

LOG_DIR = "logs"
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ─── Logging Configuration ─────────────────────────────────────────────────────────────────────────────────

def _configure_logging(verbose: bool) -> None:
    """Set up structured logging with console and file output.
    Logs are written to the logs/ directory with a timestamped filename.

    Args:
        verbose: If True, sets level to DEBUG; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Create logs directory if it doesn't exist
    os.makedirs(LOG_DIR, exist_ok=True)

    # Generate timestamped log filename (e.g., logs/headshot_upload_2026-02-27_103015.log)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"headshot_upload_{timestamp}.log")

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Console handler — prints to terminal
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    # File handler — writes to logs/ directory
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)  # Always capture full detail in file
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.info("Log file: %s", log_file)


# ─── CLI Entry Point ──────────────────────────────────────────────────────────────────────────────────────

@click.command(name="headshot-upload")
@click.option(
    "--folder",
    required=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Path to the folder containing headshot image files (JPEG).",
)
@click.option(
    "--environment",
    default="prod",
    type=click.Choice(["prod", "sandbox"], case_sensitive=False),
    show_default=True,
    help="Target Salesforce environment.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview which files would be uploaded without making API calls.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Maximum number of headshots to process.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose (DEBUG) logging output.",
)
@click.version_option(version=__version__, prog_name="headshot-upload")
def cli(
    folder: str,
    environment: str,
    dry_run: bool,
    limit: Optional[int],
    verbose: bool,
) -> None:
    """Upload headshot images to Salesforce and link them to Contact records.

    Scans the specified FOLDER for .jpg/.jpeg files whose names contain a Salesforce
    Contact ID, then uploads each image as a ContentVersion and creates a
    ContentDocumentLink to the corresponding Contact.

    \b
    Contact ID Extraction Rule:
      Filename must start with a 15- or 18-character Salesforce Contact ID
      (prefix 003), optionally followed by _<description>.
      Examples: 003AB00000Abc1DEF.jpg, 003XXXXXXXXXXXX_headshot.jpeg
    """
    # Load .env file if present (for local development)
    load_dotenv()
    _configure_logging(verbose)

    # ─── Import modules here (after logging is configured) ─────────────────────────────────────────────
    # Deferred imports keep the CLI layer thin and avoid import-time side effects
    from headshot_upload.config import ConfigurationError, load_config
    from headshot_upload.modules.auth import AuthenticationError, authenticate
    from headshot_upload.modules.scanner import scan_folder
    from headshot_upload.modules.uploader import (
        generate_dry_run_report,
        upload_headshots,
    )

    _print_header()

    # ─── Step 1: Scan folder ───────────────────────────────────────────────────────────────────────────

    click.echo(f"\n📂  Scanning folder: {folder}")

    try:
        headshot_files = scan_folder(folder)
    except (FileNotFoundError, NotADirectoryError) as exc:
        click.secho(f"\n✗  {exc}", fg="red", err=True)
        sys.exit(1)

    if not headshot_files:
        click.secho(
            "\n⚠  No valid headshot files found. Ensure filenames start with a "
            "Salesforce Contact ID (e.g., 003AB00000Abc1DEF.jpg).",
            fg="yellow",
        )
        sys.exit(0)

    # Apply --limit
    if limit is not None and limit > 0:
        headshot_files = headshot_files[:limit]

    click.echo(f"   Found {len(headshot_files)} headshot(s) to process.")

    # ─── Step 2: Dry-run mode ──────────────────────────────────────────────────────────────────────────

    if dry_run:
        _display_dry_run(headshot_files, generate_dry_run_report)
        sys.exit(0)

    # ─── Step 3: Authenticate ──────────────────────────────────────────────────────────────────────────

    click.echo(f"\n🔐  Authenticating with Salesforce ({environment})...")

    try:
        config = load_config(environment)
        session = authenticate(config)
    except ConfigurationError as exc:
        click.secho(f"\n✗  Configuration error: {exc}", fg="red", err=True)
        sys.exit(1)
    except AuthenticationError as exc:
        click.secho(f"\n✗  Authentication failed: {exc}", fg="red", err=True)
        sys.exit(1)

    click.secho("   ✓ Authenticated successfully.", fg="green")

    # ─── Step 4: Upload ────────────────────────────────────────────────────────────────────────────────

    click.echo("\n🚀  Uploading headshots...\n")

    with click.progressbar(
        length=len(headshot_files),
        label="   Progress",
        show_percent=True,
        show_pos=True,
    ) as bar:
        def progress_callback(count: int) -> None:
            bar.update(count)

        report = upload_headshots(
            session=session,
            headshot_files=headshot_files,
            progress_callback=progress_callback,
        )

    # ─── Step 5: Display results ───────────────────────────────────────────────────────────────────────

    _display_report(report)


# ─── Private — Display Helpers ─────────────────────────────────────────────────────────────────────────────

def _print_header() -> None:
    """Print the CLI tool banner."""
    click.echo("━" * 70)
    click.secho("  Headshot Upload CLI", bold=True)
    click.echo(f"  Version {__version__}")
    click.echo("━" * 70)


def _display_dry_run(headshot_files, generate_report_fn) -> None:
    """Display a dry-run preview table showing planned actions.

    Args:
        headshot_files:     List of scanned HeadshotFile objects.
        generate_report_fn: The generate_dry_run_report function from the uploader module.
    """
    click.echo("\n" + "─" * 70)
    click.secho("  DRY RUN — No API calls will be made", fg="cyan", bold=True)
    click.echo("─" * 70)

    report = generate_report_fn(headshot_files)

    for idx, entry in enumerate(report, start=1):
        click.echo(f"\n  {idx}. {entry['filename']}")
        click.echo(f"     Contact ID : {entry['contact_id']}")
        click.echo(f"     File size  : {entry['file_size']}")
        click.echo(f"     Action     : {entry['action']}")

    click.echo("\n" + "─" * 70)
    click.echo(f"  Total: {len(report)} file(s) would be processed.")
    click.echo("─" * 70)


def _display_report(report) -> None:
    """Display the final upload results.

    Args:
        report: UploadReport from the uploader module.
    """
    click.echo("\n" + "━" * 70)
    click.secho("  Upload Results", bold=True)
    click.echo("━" * 70)

    # Per-file results
    for result in report.results:
        if result.success:
            click.secho(f"  ✓  {result.filename}", fg="green")
            click.echo(f"     Contact: {result.contact_id}")
            click.echo(f"     CV: {result.content_version_id}  |  CDL: {result.content_document_link_id}")
        else:
            click.secho(f"  ✗  {result.filename}", fg="red")
            click.echo(f"     Contact: {result.contact_id}")
            click.echo(f"     Error: {result.error}")

    # Summary
    click.echo("\n" + "─" * 70)
    click.echo(f"  Total      : {report.total}")
    click.secho(f"  Successful : {report.successful}", fg="green")

    if report.failed > 0:
        click.secho(f"  Failed     : {report.failed}", fg="red")
    else:
        click.echo(f"  Failed     : {report.failed}")

    click.echo(f"  Success %  : {report.success_rate:.1f}%")
    click.echo("━" * 70)
