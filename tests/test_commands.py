"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            test_commands.py
@Purpose         Tests for the CLI command layer — option parsing, dry-run output, error display,
                 and integration with the Click test runner.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from headshot_upload.cli.commands import cli
from headshot_upload.modules.scanner import HeadshotFile
from headshot_upload.modules.salesforce_api import (
    ContentDocumentLinkResult,
    ContentVersionResult,
)
from headshot_upload.modules.uploader import UploadReport, UploadResult
from tests.conftest import CONTACT_ID_18_A, CONTACT_ID_18_B, MINIMAL_JPEG_BYTES

__author__ = "Marimuthu V S"


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


# ─── Option Parsing Tests ───────────────────────────────────────────────────────────────────────────────────

class TestCliOptionParsing:
    """Tests for CLI option validation and parsing."""

    def test_folder_required(self, runner):
        """CLI should fail when --folder is not provided."""
        result = runner.invoke(cli, [])
        assert result.exit_code != 0, "Should fail without required --folder"
        assert "Missing option" in result.output or "Error" in result.output, "Should show error about missing --folder"

    def test_invalid_folder_path(self, runner):
        """CLI should fail when --folder points to a non-existent directory."""
        result = runner.invoke(cli, ["--folder", "/nonexistent/path/12345"])
        assert result.exit_code != 0, "Should fail with invalid folder path"

    def test_version_flag(self, runner):
        """--version should display the version number and exit."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0, "Should exit cleanly"
        assert "1.0.0" in result.output, "Should display version number"


# ─── Dry Run Tests ──────────────────────────────────────────────────────────────────────────────────────────

class TestCliDryRun:
    """Tests for the --dry-run flag."""

    def test_dry_run_displays_preview(self, runner, tmp_path):
        """Dry-run mode should show file details without making API calls."""
        # Create a valid headshot file
        (tmp_path / f"{CONTACT_ID_18_A}.jpg").write_bytes(MINIMAL_JPEG_BYTES)

        result = runner.invoke(cli, ["--folder", str(tmp_path), "--dry-run"])

        assert result.exit_code == 0, f"Should exit cleanly, got: {result.output}"
        assert "DRY RUN" in result.output, "Should indicate dry-run mode"
        assert CONTACT_ID_18_A in result.output, "Should show the Contact ID"

    def test_dry_run_with_limit(self, runner, tmp_path):
        """Dry-run with --limit should only show the limited number of files."""
        (tmp_path / f"{CONTACT_ID_18_A}.jpg").write_bytes(MINIMAL_JPEG_BYTES)
        (tmp_path / f"{CONTACT_ID_18_B}.jpg").write_bytes(MINIMAL_JPEG_BYTES)

        result = runner.invoke(cli, ["--folder", str(tmp_path), "--dry-run", "--limit", "1"])

        assert result.exit_code == 0, "Should exit cleanly"
        assert "1 file(s)" in result.output, "Should show 1 file in total"


# ─── Empty Folder Tests ─────────────────────────────────────────────────────────────────────────────────────

class TestCliEmptyFolder:
    """Tests for running the CLI against an empty folder."""

    def test_empty_folder_shows_warning(self, runner, tmp_path):
        """Empty folder should print a warning and exit gracefully."""
        result = runner.invoke(cli, ["--folder", str(tmp_path)])

        assert result.exit_code == 0, "Should exit cleanly with code 0"
        assert "No valid headshot files found" in result.output, "Should show warning message"


# ─── Upload Flow Tests ──────────────────────────────────────────────────────────────────────────────────────

class TestCliUploadFlow:
    """Tests for the full upload flow through the CLI."""

    @patch("headshot_upload.modules.uploader.upload_headshots")
    @patch("headshot_upload.modules.auth.authenticate")
    @patch("headshot_upload.config.load_config")
    def test_successful_upload_displays_results(
        self, mock_load_config, mock_auth, mock_upload, runner, tmp_path
    ):
        """Successful upload should display results with success indicators."""
        # Create test file
        (tmp_path / f"{CONTACT_ID_18_A}.jpg").write_bytes(MINIMAL_JPEG_BYTES)

        # Set up mocks
        mock_load_config.return_value = MagicMock()
        mock_auth.return_value = MagicMock()
        mock_upload.return_value = UploadReport(
            total=1,
            successful=1,
            failed=0,
            results=[
                UploadResult(
                    contact_id=CONTACT_ID_18_A,
                    filename=f"{CONTACT_ID_18_A}.jpg",
                    success=True,
                    content_version_id="068AAA",
                    content_document_link_id="06ACCC",
                ),
            ],
        )

        result = runner.invoke(cli, ["--folder", str(tmp_path)])

        assert result.exit_code == 0, f"Should exit cleanly, got: {result.output}"
        assert "Successful" in result.output, "Should show success summary"
        assert "068AAA" in result.output, "Should display ContentVersion ID"
