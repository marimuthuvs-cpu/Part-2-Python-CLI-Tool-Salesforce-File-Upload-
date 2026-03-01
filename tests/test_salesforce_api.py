"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            test_salesforce_api.py
@Purpose         Tests for the Salesforce API module — Composite API calls for ContentVersion and
                 ContentDocumentLink creation, SOQL queries, retry logic, and error handling.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import pytest
import responses

from headshot_upload.modules.salesforce_api import (
    ContentDocumentLinkData,
    ContentDocumentLinkResult,
    ContentVersionResult,
    HeadshotPayload,
    SalesforceApiError,
    create_content_document_links,
    create_content_versions,
    query_content_document_ids,
)

__author__ = "Marimuthu V S"


# ─── Helpers ─────────────────────────────────────────────────────────────────────────────────────────────────

def _make_payload(contact_id: str = "003AB00000Abc1DEFA", index: int = 0) -> HeadshotPayload:
    """Build a test HeadshotPayload."""
    return HeadshotPayload(
        contact_id=contact_id,
        filename=f"{contact_id}_headshot.jpg",
        title=f"Headshot — {contact_id}",
        base64_data="dGVzdA==",  # base64 of "test"
    )


def _composite_success_response(ref_id: str, record_id: str) -> dict:
    """Build a Composite API sub-response for a successful creation."""
    return {
        "body": {"id": record_id, "success": True, "errors": []},
        "httpHeaders": {},
        "httpStatusCode": 201,
        "referenceId": ref_id,
    }


def _composite_error_response(ref_id: str, message: str = "Required field missing") -> dict:
    """Build a Composite API sub-response for a failed creation."""
    return {
        "body": [{"message": message, "errorCode": "REQUIRED_FIELD_MISSING", "fields": []}],
        "httpHeaders": {},
        "httpStatusCode": 400,
        "referenceId": ref_id,
    }


# ─── ContentVersion Creation Tests ───────────────────────────────────────────────────────────────────────────

class TestCreateContentVersions:
    """Tests for Composite API ContentVersion creation."""

    @responses.activate
    def test_create_content_versions_success(self, mock_session):
        """Successful ContentVersion creation returns results with content_version_id populated."""
        responses.add(
            responses.POST,
            f"{mock_session.instance_url}/services/data/v65.0/composite",
            json={
                "compositeResponse": [
                    _composite_success_response("cv_0", "068000000000001AAA"),
                ]
            },
            status=200,
        )

        payloads = [_make_payload()]
        results = create_content_versions(mock_session, payloads)

        assert len(results) == 1, "Should return one result per payload"
        assert results[0].success is True, "Result should be successful"
        assert results[0].content_version_id == "068000000000001AAA", "CV ID should be populated"
        assert results[0].contact_id == "003AB00000Abc1DEFA", "Contact ID should match"

    @responses.activate
    def test_create_content_versions_partial_failure(self, mock_session):
        """When some sub-requests fail, results reflect per-item success/failure."""
        responses.add(
            responses.POST,
            f"{mock_session.instance_url}/services/data/v65.0/composite",
            json={
                "compositeResponse": [
                    _composite_success_response("cv_0", "068000000000001AAA"),
                    _composite_error_response("cv_1", "Title is required"),
                ]
            },
            status=200,
        )

        payloads = [
            _make_payload("003AB00000Abc1DEFA"),
            _make_payload("003CD00000Xyz9GHIA"),
        ]
        results = create_content_versions(mock_session, payloads)

        assert len(results) == 2, "Should return one result per payload"
        assert results[0].success is True, "First should succeed"
        assert results[1].success is False, "Second should fail"
        assert "Title is required" in (results[1].error or ""), "Error message should be propagated"

    @responses.activate
    def test_create_content_versions_http_error(self, mock_session):
        """HTTP-level error (e.g., 401) returns all items as failed."""
        responses.add(
            responses.POST,
            f"{mock_session.instance_url}/services/data/v65.0/composite",
            json=[{"message": "Session expired", "errorCode": "INVALID_SESSION_ID"}],
            status=401,
        )

        payloads = [_make_payload()]
        results = create_content_versions(mock_session, payloads)

        assert len(results) == 1, "Should return one result per payload"
        assert results[0].success is False, "Should be marked as failed"
        assert results[0].error is not None, "Error message should be populated"

    def test_create_content_versions_empty_list(self, mock_session):
        """Empty payload list returns empty results without making API calls."""
        results = create_content_versions(mock_session, [])
        assert results == [], "Empty input should return empty output"


# ─── ContentDocumentId Query Tests ───────────────────────────────────────────────────────────────────────────

class TestQueryContentDocumentIds:
    """Tests for SOQL query to retrieve ContentDocumentIds."""

    @responses.activate
    def test_query_content_document_ids_success(self, mock_session):
        """Successful query returns a mapping of CV ID → ContentDocument ID."""
        responses.add(
            responses.GET,
            f"{mock_session.instance_url}/services/data/v65.0/query",
            json={
                "totalSize": 1,
                "done": True,
                "records": [
                    {
                        "attributes": {"type": "ContentVersion"},
                        "Id": "068000000000001AAA",
                        "ContentDocumentId": "069000000000001AAA",
                    }
                ],
            },
            status=200,
        )

        result = query_content_document_ids(mock_session, ["068000000000001AAA"])

        assert "068000000000001AAA" in result, "CV ID should be in the result map"
        assert result["068000000000001AAA"] == "069000000000001AAA", "Should map to correct Doc ID"

    def test_query_content_document_ids_empty_list(self, mock_session):
        """Empty input list returns empty mapping without making API calls."""
        result = query_content_document_ids(mock_session, [])
        assert result == {}, "Empty input should return empty dict"


# ─── ContentDocumentLink Creation Tests ──────────────────────────────────────────────────────────────────────

class TestCreateContentDocumentLinks:
    """Tests for Composite API ContentDocumentLink creation."""

    @responses.activate
    def test_create_content_document_links_success(self, mock_session):
        """Successful CDL creation returns results with IDs populated."""
        responses.add(
            responses.POST,
            f"{mock_session.instance_url}/services/data/v65.0/composite",
            json={
                "compositeResponse": [
                    _composite_success_response("cdl_0", "06A000000000001AAA"),
                ]
            },
            status=200,
        )

        link_data = [
            ContentDocumentLinkData(
                content_document_id="069000000000001AAA",
                linked_entity_id="003AB00000Abc1DEFA",
            )
        ]
        results = create_content_document_links(mock_session, link_data)

        assert len(results) == 1, "Should return one result per link"
        assert results[0].success is True, "Result should be successful"
        assert results[0].content_document_link_id == "06A000000000001AAA", "CDL ID should be populated"

    @responses.activate
    def test_create_content_document_links_failure(self, mock_session):
        """Failed CDL creation returns error details."""
        responses.add(
            responses.POST,
            f"{mock_session.instance_url}/services/data/v65.0/composite",
            json={
                "compositeResponse": [
                    _composite_error_response("cdl_0", "Insufficient access"),
                ]
            },
            status=200,
        )

        link_data = [
            ContentDocumentLinkData(
                content_document_id="069000000000001AAA",
                linked_entity_id="003AB00000Abc1DEFA",
            )
        ]
        results = create_content_document_links(mock_session, link_data)

        assert len(results) == 1, "Should return one result"
        assert results[0].success is False, "Should be marked as failed"
        assert "Insufficient access" in (results[0].error or ""), "Error message should be included"

    def test_create_content_document_links_empty_list(self, mock_session):
        """Empty input returns empty results without API calls."""
        results = create_content_document_links(mock_session, [])
        assert results == [], "Empty input should return empty output"


# ─── Retry Logic Tests ──────────────────────────────────────────────────────────────────────────────────────

class TestRetryLogic:
    """Tests for automatic retry on transient HTTP errors."""

    @responses.activate
    def test_retry_on_500_then_success(self, mock_session):
        """A transient 500 error followed by a 200 should succeed after retry."""
        # First call: 500 error
        responses.add(
            responses.POST,
            f"{mock_session.instance_url}/services/data/v65.0/composite",
            json={"message": "Internal Server Error"},
            status=500,
        )
        # Second call: success
        responses.add(
            responses.POST,
            f"{mock_session.instance_url}/services/data/v65.0/composite",
            json={
                "compositeResponse": [
                    _composite_success_response("cv_0", "068000000000001AAA"),
                ]
            },
            status=200,
        )

        payloads = [_make_payload()]
        results = create_content_versions(mock_session, payloads)

        assert len(results) == 1, "Should return results after retry"
        assert results[0].success is True, "Should succeed after retry"

    @responses.activate
    def test_exhausted_retries_returns_failure(self, mock_session):
        """When all retries are exhausted, results should indicate failure."""
        # All calls return 500
        for _ in range(4):  # MAX_RETRIES + 1
            responses.add(
                responses.POST,
                f"{mock_session.instance_url}/services/data/v65.0/composite",
                json={"message": "Internal Server Error"},
                status=500,
            )

        payloads = [_make_payload()]
        results = create_content_versions(mock_session, payloads)

        assert len(results) == 1, "Should return one result"
        assert results[0].success is False, "Should be failed after exhausted retries"
