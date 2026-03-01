"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            test_uploader.py
@Purpose         Tests for the uploader orchestration module — full upload flow, dry run, batching,
                 partial failure, and edge cases.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from headshot_upload.modules.scanner import HeadshotFile
from headshot_upload.modules.salesforce_api import (
    ContentDocumentLinkResult,
    ContentVersionResult,
)
from headshot_upload.modules.uploader import (
    UploadReport,
    UploadResult,
    generate_dry_run_report,
    upload_headshots,
)
from tests.conftest import CONTACT_ID_18_A, CONTACT_ID_18_B, MINIMAL_JPEG_BYTES

__author__ = "Marimuthu V S"


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────────────────────────

def _make_headshot_file(tmp_path: Path, contact_id: str, suffix: str = "") -> HeadshotFile:
    """Create a temporary headshot file and return a HeadshotFile object."""
    filename = f"{contact_id}{suffix}.jpg"
    file_path = tmp_path / filename
    file_path.write_bytes(MINIMAL_JPEG_BYTES)
    return HeadshotFile(file_path=file_path, filename=filename, contact_id=contact_id)


# ─── Success Scenarios ───────────────────────────────────────────────────────────────────────────────────────

class TestUploadHeadshotsSuccess:
    """Tests for the full upload flow — happy path."""

    @patch("headshot_upload.modules.uploader.create_content_document_links")
    @patch("headshot_upload.modules.uploader.query_content_document_ids")
    @patch("headshot_upload.modules.uploader.create_content_versions")
    @patch("headshot_upload.modules.uploader.encode_file_to_base64")
    def test_upload_success_end_to_end(
        self, mock_encode, mock_create_cv, mock_query, mock_create_cdl, mock_session, tmp_path
    ):
        """Full upload flow: encode → create CV → query DocIds → create CDL."""
        hf = _make_headshot_file(tmp_path, CONTACT_ID_18_A, "_headshot")

        mock_encode.return_value = "dGVzdA=="
        mock_create_cv.return_value = [
            ContentVersionResult(contact_id=CONTACT_ID_18_A, success=True, content_version_id="068AAA"),
        ]
        mock_query.return_value = {"068AAA": "069BBB"}
        mock_create_cdl.return_value = [
            ContentDocumentLinkResult(contact_id=CONTACT_ID_18_A, success=True, content_document_link_id="06ACCC"),
        ]

        report = upload_headshots(mock_session, [hf])

        assert report.total == 1, "Should process 1 file"
        assert report.successful == 1, "Should have 1 success"
        assert report.failed == 0, "Should have 0 failures"
        assert report.results[0].success is True, "Result should be successful"
        assert report.results[0].content_version_id == "068AAA", "CV ID should be set"
        assert report.results[0].content_document_link_id == "06ACCC", "CDL ID should be set"


# ─── Failure Scenarios ───────────────────────────────────────────────────────────────────────────────────────

class TestUploadHeadshotsFailure:
    """Tests for error handling during upload."""

    @patch("headshot_upload.modules.uploader.create_content_versions")
    @patch("headshot_upload.modules.uploader.encode_file_to_base64")
    def test_upload_encoding_failure(self, mock_encode, mock_create_cv, mock_session, tmp_path):
        """When file encoding fails, the file is reported as failed without calling the API."""
        from headshot_upload.modules.encoder import EncodingError

        hf = _make_headshot_file(tmp_path, CONTACT_ID_18_A)
        mock_encode.side_effect = EncodingError("Cannot read file")

        report = upload_headshots(mock_session, [hf])

        assert report.total == 1, "Should report 1 total"
        assert report.failed == 1, "Should report 1 failure"
        assert "Encoding failed" in report.results[0].error, "Error should mention encoding"
        mock_create_cv.assert_not_called()

    @patch("headshot_upload.modules.uploader.create_content_versions")
    @patch("headshot_upload.modules.uploader.encode_file_to_base64")
    def test_upload_cv_creation_failure(self, mock_encode, mock_create_cv, mock_session, tmp_path):
        """When ContentVersion creation fails, the file is reported as failed."""
        hf = _make_headshot_file(tmp_path, CONTACT_ID_18_A)

        mock_encode.return_value = "dGVzdA=="
        mock_create_cv.return_value = [
            ContentVersionResult(contact_id=CONTACT_ID_18_A, success=False, error="Limit exceeded"),
        ]

        report = upload_headshots(mock_session, [hf])

        assert report.total == 1, "Should report 1 total"
        assert report.failed == 1, "Should report 1 failure"
        assert "ContentVersion creation failed" in report.results[0].error, "Error should reference CV"

    @patch("headshot_upload.modules.uploader.create_content_document_links")
    @patch("headshot_upload.modules.uploader.query_content_document_ids")
    @patch("headshot_upload.modules.uploader.create_content_versions")
    @patch("headshot_upload.modules.uploader.encode_file_to_base64")
    def test_upload_cdl_creation_failure(
        self, mock_encode, mock_create_cv, mock_query, mock_create_cdl, mock_session, tmp_path
    ):
        """When ContentDocumentLink creation fails, the file is reported as failed."""
        hf = _make_headshot_file(tmp_path, CONTACT_ID_18_A)

        mock_encode.return_value = "dGVzdA=="
        mock_create_cv.return_value = [
            ContentVersionResult(contact_id=CONTACT_ID_18_A, success=True, content_version_id="068AAA"),
        ]
        mock_query.return_value = {"068AAA": "069BBB"}
        mock_create_cdl.return_value = [
            ContentDocumentLinkResult(contact_id=CONTACT_ID_18_A, success=False, error="Insufficient access"),
        ]

        report = upload_headshots(mock_session, [hf])

        assert report.total == 1, "Should report 1 total"
        assert report.failed == 1, "Should report 1 failure"
        assert "ContentDocumentLink creation failed" in report.results[0].error, "Error should reference CDL"


# ─── Edge Cases ──────────────────────────────────────────────────────────────────────────────────────────────

class TestUploadHeadshotsEdgeCases:
    """Tests for edge cases — empty input, progress callbacks, batching."""

    def test_upload_empty_list_returns_empty_report(self, mock_session):
        """Uploading an empty list returns a report with all zeros."""
        report = upload_headshots(mock_session, [])

        assert report.total == 0, "Total should be 0"
        assert report.successful == 0, "Successful should be 0"
        assert report.failed == 0, "Failed should be 0"
        assert report.results == [], "Results should be empty"

    @patch("headshot_upload.modules.uploader.create_content_document_links")
    @patch("headshot_upload.modules.uploader.query_content_document_ids")
    @patch("headshot_upload.modules.uploader.create_content_versions")
    @patch("headshot_upload.modules.uploader.encode_file_to_base64")
    def test_upload_progress_callback_invoked(
        self, mock_encode, mock_create_cv, mock_query, mock_create_cdl, mock_session, tmp_path
    ):
        """Progress callback should be called with the batch size."""
        hf = _make_headshot_file(tmp_path, CONTACT_ID_18_A)

        mock_encode.return_value = "dGVzdA=="
        mock_create_cv.return_value = [
            ContentVersionResult(contact_id=CONTACT_ID_18_A, success=True, content_version_id="068AAA"),
        ]
        mock_query.return_value = {"068AAA": "069BBB"}
        mock_create_cdl.return_value = [
            ContentDocumentLinkResult(contact_id=CONTACT_ID_18_A, success=True, content_document_link_id="06ACCC"),
        ]

        callback = MagicMock()
        upload_headshots(mock_session, [hf], progress_callback=callback)

        callback.assert_called_once_with(1)


# ─── Dry Run Tests ───────────────────────────────────────────────────────────────────────────────────────────

class TestDryRun:
    """Tests for the dry-run report generation."""

    def test_dry_run_report_format(self, tmp_path):
        """Dry-run report should contain filename, contact_id, file_size, and action for each file."""
        hf = _make_headshot_file(tmp_path, CONTACT_ID_18_A, "_headshot")
        report = generate_dry_run_report([hf])

        assert len(report) == 1, "Should produce one entry per file"
        entry = report[0]
        assert entry["filename"] == f"{CONTACT_ID_18_A}_headshot.jpg", "Filename should match"
        assert entry["contact_id"] == CONTACT_ID_18_A, "Contact ID should match"
        assert "file_size" in entry, "Should include file_size"
        assert "action" in entry, "Should include planned action"

    def test_dry_run_empty_list(self):
        """Dry-run with no files returns an empty list."""
        report = generate_dry_run_report([])
        assert report == [], "Empty input should produce empty report"


# ─── Upload Report Tests ────────────────────────────────────────────────────────────────────────────────────

class TestUploadReport:
    """Tests for the UploadReport data class."""

    def test_success_rate_calculation(self):
        """Success rate should be calculated correctly."""
        report = UploadReport(total=10, successful=7, failed=3)
        assert report.success_rate == 70.0, "Success rate should be 70%"

    def test_success_rate_zero_total(self):
        """Success rate with zero total should be 0.0 (not division by zero)."""
        report = UploadReport(total=0, successful=0, failed=0)
        assert report.success_rate == 0.0, "Zero total should yield 0.0% rate"

    def test_success_rate_all_success(self):
        """100% success rate when all uploads succeed."""
        report = UploadReport(total=5, successful=5, failed=0)
        assert report.success_rate == 100.0, "Should be 100%"
