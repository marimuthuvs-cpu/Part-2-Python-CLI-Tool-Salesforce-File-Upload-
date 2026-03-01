"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            salesforce_api.py
@TestClass       test_salesforce_api.py
@Purpose         Salesforce REST and Composite API interactions. Handles ContentVersion creation,
                 ContentDocumentId querying, and ContentDocumentLink creation with automatic batching,
                 retry logic for transient errors, and partial-success support.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

from headshot_upload.config import (
    CDL_COMPOSITE_BATCH_SIZE,
    CV_COMPOSITE_BATCH_SIZE,
    QUERY_BATCH_SIZE,
)
from headshot_upload.modules.auth import SalesforceSession

__author__ = "Marimuthu V S"

logger = logging.getLogger(__name__)


# ─── Constants ─────────────────────────────────────────────────────────────────────────────────────────────

# HTTP status codes eligible for automatic retry with exponential back-off
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 1.0


# ─── Exceptions ────────────────────────────────────────────────────────────────────────────────────────────

class SalesforceApiError(Exception):
    """Raised when a Salesforce API call fails after all retries are exhausted."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


# ─── Data Classes ──────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class HeadshotPayload:
    """Prepared data for a single ContentVersion creation request."""

    contact_id: str
    filename: str
    title: str
    base64_data: str


@dataclass
class ContentVersionResult:
    """Result of a single ContentVersion creation attempt."""

    contact_id: str
    success: bool
    content_version_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ContentDocumentLinkData:
    """Input data for a single ContentDocumentLink creation request."""

    content_document_id: str
    linked_entity_id: str


@dataclass
class ContentDocumentLinkResult:
    """Result of a single ContentDocumentLink creation attempt."""

    contact_id: str
    success: bool
    content_document_link_id: Optional[str] = None
    error: Optional[str] = None


# ─── Public Functions ──────────────────────────────────────────────────────────────────────────────────────

def create_content_versions(
    session: SalesforceSession,
    payloads: List[HeadshotPayload],
) -> List[ContentVersionResult]:
    """Create ContentVersion records in Salesforce using the Composite API.
    Splits payloads into batches of CV_COMPOSITE_BATCH_SIZE automatically.

    Args:
        session:  Authenticated SalesforceSession.
        payloads: List of HeadshotPayload objects to upload.

    Returns:
        List of ContentVersionResult — one per input payload, preserving order.
    """
    if not payloads:
        return []

    all_results: List[ContentVersionResult] = []

    for chunk in _chunks(payloads, CV_COMPOSITE_BATCH_SIZE):
        results = _create_cv_composite_batch(session, chunk)
        all_results.extend(results)

    logger.info(
        "ContentVersion creation complete — %d succeeded, %d failed",
        sum(1 for r in all_results if r.success),
        sum(1 for r in all_results if not r.success),
    )
    return all_results


def query_content_document_ids(
    session: SalesforceSession,
    content_version_ids: List[str],
) -> Dict[str, str]:
    """Query the ContentDocumentId for each given ContentVersion record.
    Retrieves the auto-generated ContentDocument mapping needed for ContentDocumentLink creation.

    Args:
        session:             Authenticated SalesforceSession.
        content_version_ids: List of ContentVersion record IDs to look up.

    Returns:
        Dict mapping ContentVersion.Id to ContentVersion.ContentDocumentId.

    Raises:
        SalesforceApiError: If the SOQL query fails.
    """
    if not content_version_ids:
        return {}

    result_map: Dict[str, str] = {}

    for chunk in _chunks(content_version_ids, QUERY_BATCH_SIZE):
        ids_clause = ", ".join(f"'{cv_id}'" for cv_id in chunk)
        soql = (
            "SELECT Id, ContentDocumentId "
            "FROM ContentVersion "
            f"WHERE Id IN ({ids_clause})"
        )

        response = _make_request(
            session,
            method="GET",
            url=f"{session.base_url}/query",
            params={"q": soql},
        )
        data = response.json()

        for record in data.get("records", []):
            result_map[record["Id"]] = record["ContentDocumentId"]

    logger.info(
        "ContentDocumentId query complete — %d mapping(s) retrieved",
        len(result_map),
    )
    return result_map


def create_content_document_links(
    session: SalesforceSession,
    link_data: List[ContentDocumentLinkData],
) -> List[ContentDocumentLinkResult]:
    """Create ContentDocumentLink records to link ContentDocuments to Contact records.
    Automatically batches into chunks of CDL_COMPOSITE_BATCH_SIZE.

    Args:
        session:   Authenticated SalesforceSession.
        link_data: List of ContentDocumentLinkData describing the links to create.

    Returns:
        List of ContentDocumentLinkResult — one per input, preserving order.
    """
    if not link_data:
        return []

    all_results: List[ContentDocumentLinkResult] = []

    for chunk in _chunks(link_data, CDL_COMPOSITE_BATCH_SIZE):
        results = _create_cdl_composite_batch(session, chunk)
        all_results.extend(results)

    logger.info(
        "ContentDocumentLink creation complete — %d succeeded, %d failed",
        sum(1 for r in all_results if r.success),
        sum(1 for r in all_results if not r.success),
    )
    return all_results


# ─── Private — Composite API Batches ──────────────────────────────────────────────────────────────────────

def _create_cv_composite_batch(
    session: SalesforceSession,
    payloads: List[HeadshotPayload],
) -> List[ContentVersionResult]:
    """Create a batch of ContentVersion records via a single Composite API call.

    Args:
        session:  Authenticated SalesforceSession.
        payloads: List of HeadshotPayload (max CV_COMPOSITE_BATCH_SIZE).

    Returns:
        List of ContentVersionResult — one per payload.
    """
    ref_id_map: Dict[str, HeadshotPayload] = {}
    composite_sub_requests = []

    for idx, payload in enumerate(payloads):
        ref_id = f"cv_{idx}"
        ref_id_map[ref_id] = payload
        composite_sub_requests.append({
            "method": "POST",
            "url": f"/services/data/v{session.api_version}/sobjects/ContentVersion",
            "referenceId": ref_id,
            "body": {
                "Title": payload.title,
                "PathOnClient": payload.filename,
                "VersionData": payload.base64_data,
                "Description": f"Headshot for Contact {payload.contact_id}",
            },
        })

    composite_body = {
        "allOrNone": False,
        "compositeRequest": composite_sub_requests,
    }

    try:
        response = _make_request(
            session,
            method="POST",
            url=f"{session.base_url}/composite",
            json_body=composite_body,
        )
        return _parse_cv_composite_response(response.json(), ref_id_map)

    except SalesforceApiError as exc:
        logger.error("Composite ContentVersion batch failed: %s", exc)
        return [
            ContentVersionResult(
                contact_id=p.contact_id,
                success=False,
                error=str(exc),
            )
            for p in payloads
        ]


def _create_cdl_composite_batch(
    session: SalesforceSession,
    link_data: List[ContentDocumentLinkData],
) -> List[ContentDocumentLinkResult]:
    """Create a batch of ContentDocumentLink records via a single Composite API call.

    Args:
        session:   Authenticated SalesforceSession.
        link_data: List of ContentDocumentLinkData (max CDL_COMPOSITE_BATCH_SIZE).

    Returns:
        List of ContentDocumentLinkResult — one per input.
    """
    ref_id_map: Dict[str, ContentDocumentLinkData] = {}
    composite_sub_requests = []

    for idx, link in enumerate(link_data):
        ref_id = f"cdl_{idx}"
        ref_id_map[ref_id] = link
        composite_sub_requests.append({
            "method": "POST",
            "url": f"/services/data/v{session.api_version}/sobjects/ContentDocumentLink",
            "referenceId": ref_id,
            "body": {
                "ContentDocumentId": link.content_document_id,
                "LinkedEntityId": link.linked_entity_id,
                "ShareType": "V",
                "Visibility": "AllUsers",
            },
        })

    composite_body = {
        "allOrNone": False,
        "compositeRequest": composite_sub_requests,
    }

    try:
        response = _make_request(
            session,
            method="POST",
            url=f"{session.base_url}/composite",
            json_body=composite_body,
        )
        return _parse_cdl_composite_response(response.json(), ref_id_map)

    except SalesforceApiError as exc:
        logger.error("Composite ContentDocumentLink batch failed: %s", exc)
        return [
            ContentDocumentLinkResult(
                contact_id=link.linked_entity_id,
                success=False,
                error=str(exc),
            )
            for link in link_data
        ]


# ─── Private — Response Parsing ───────────────────────────────────────────────────────────────────────────

def _parse_cv_composite_response(
    data: dict,
    ref_id_map: Dict[str, HeadshotPayload],
) -> List[ContentVersionResult]:
    """Parse the Composite API response for ContentVersion creation sub-requests.

    Args:
        data:       Parsed JSON response body from the Composite API.
        ref_id_map: Mapping of referenceId to HeadshotPayload.

    Returns:
        List of ContentVersionResult.
    """
    results: List[ContentVersionResult] = []

    for sub_resp in data.get("compositeResponse", []):
        ref_id = sub_resp.get("referenceId", "")
        payload = ref_id_map.get(ref_id)
        contact_id = payload.contact_id if payload else "unknown"
        http_status = sub_resp.get("httpStatusCode", 0)
        body = sub_resp.get("body", {})

        if 200 <= http_status < 300 and isinstance(body, dict) and body.get("success"):
            results.append(ContentVersionResult(
                contact_id=contact_id,
                success=True,
                content_version_id=body["id"],
            ))
        else:
            error_msg = _extract_error_message(body)
            logger.error(
                "ContentVersion creation failed for Contact %s — %s",
                contact_id,
                error_msg,
            )
            results.append(ContentVersionResult(
                contact_id=contact_id,
                success=False,
                error=error_msg,
            ))

    return results


def _parse_cdl_composite_response(
    data: dict,
    ref_id_map: Dict[str, ContentDocumentLinkData],
) -> List[ContentDocumentLinkResult]:
    """Parse the Composite API response for ContentDocumentLink creation sub-requests.

    Args:
        data:       Parsed JSON response body from the Composite API.
        ref_id_map: Mapping of referenceId to ContentDocumentLinkData.

    Returns:
        List of ContentDocumentLinkResult.
    """
    results: List[ContentDocumentLinkResult] = []

    for sub_resp in data.get("compositeResponse", []):
        ref_id = sub_resp.get("referenceId", "")
        link = ref_id_map.get(ref_id)
        contact_id = link.linked_entity_id if link else "unknown"
        http_status = sub_resp.get("httpStatusCode", 0)
        body = sub_resp.get("body", {})

        if 200 <= http_status < 300 and isinstance(body, dict) and body.get("success"):
            results.append(ContentDocumentLinkResult(
                contact_id=contact_id,
                success=True,
                content_document_link_id=body["id"],
            ))
        else:
            error_msg = _extract_error_message(body)
            logger.error(
                "ContentDocumentLink creation failed for Contact %s — %s",
                contact_id,
                error_msg,
            )
            results.append(ContentDocumentLinkResult(
                contact_id=contact_id,
                success=False,
                error=error_msg,
            ))

    return results


# ─── Private — HTTP Helper with Retry ─────────────────────────────────────────────────────────────────────

def _make_request(
    session: SalesforceSession,
    method: str,
    url: str,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
    max_retries: int = MAX_RETRIES,
) -> requests.Response:
    """Execute an HTTP request against the Salesforce REST API with retry logic.
    Retries on transient HTTP errors (429, 5xx) using exponential back-off.

    Args:
        session:     Authenticated SalesforceSession providing headers.
        method:      HTTP method ("GET", "POST", etc.).
        url:         Fully qualified request URL.
        json_body:   Optional JSON-serialisable request body.
        params:      Optional URL query parameters.
        max_retries: Maximum retry attempts for transient errors.

    Returns:
        The successful requests.Response object.

    Raises:
        SalesforceApiError: If the request fails after all retries.
    """
    for attempt in range(max_retries + 1):
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=session.headers,
                json=json_body,
                params=params,
                timeout=120,
            )
        except requests.exceptions.RequestException as exc:
            if attempt < max_retries:
                _wait_and_log_retry(attempt, max_retries, str(exc))
                continue
            raise SalesforceApiError(
                f"Request failed after {max_retries + 1} attempts: {exc}"
            ) from exc

        # Retry on transient server/rate-limit errors
        if response.status_code in RETRYABLE_STATUS_CODES:
            if attempt < max_retries:
                _wait_and_log_retry(
                    attempt, max_retries, f"HTTP {response.status_code}"
                )
                continue
            raise SalesforceApiError(
                f"HTTP {response.status_code} after {max_retries + 1} attempts",
                status_code=response.status_code,
            )

        # Non-retryable client/server error
        if response.status_code >= 400:
            detail = _extract_response_error(response)
            raise SalesforceApiError(
                f"HTTP {response.status_code}: {detail}",
                status_code=response.status_code,
            )

        return response

    # Defensive — should never be reached
    raise SalesforceApiError("Request failed: exhausted all retries")


# ─── Private — Utilities ──────────────────────────────────────────────────────────────────────────────────

def _wait_and_log_retry(attempt: int, max_retries: int, reason: str) -> None:
    """Log a retry warning and sleep with exponential back-off.

    Args:
        attempt:     Zero-based attempt index.
        max_retries: Maximum number of retry attempts allowed.
        reason:      Human-readable reason for the retry.
    """
    delay = RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
    logger.warning(
        "Retryable error (attempt %d/%d): %s — retrying in %.1fs",
        attempt + 1,
        max_retries,
        reason,
        delay,
    )
    time.sleep(delay)


def _extract_error_message(body) -> str:
    """Extract a human-readable error message from a Composite API sub-response body.
    Handles list of error dicts, dict with errors array, or raw body fallback.

    Args:
        body: Parsed JSON body of a Composite API sub-response.

    Returns:
        Concatenated error message string.
    """
    if isinstance(body, list):
        messages = [item.get("message", str(item)) for item in body if isinstance(item, dict)]
        return "; ".join(messages) if messages else str(body)

    if isinstance(body, dict):
        errors = body.get("errors", [])
        if errors:
            return "; ".join(str(e) for e in errors)
        if "message" in body:
            return body["message"]

    return str(body)[:500]


def _extract_response_error(response: requests.Response) -> str:
    """Extract an error description from a non-200 HTTP response.

    Args:
        response: The requests.Response object.

    Returns:
        Human-readable error description.
    """
    try:
        data = response.json()
        if isinstance(data, list):
            return "; ".join(
                item.get("message", str(item)) for item in data if isinstance(item, dict)
            )
        if isinstance(data, dict):
            return data.get("message", data.get("error_description", str(data)))
    except ValueError:
        pass
    return response.text[:500]


def _chunks(lst: list, size: int):
    """Yield successive chunks of the given size from lst.

    Args:
        lst:  The list to split.
        size: Maximum chunk size.
    """
    for i in range(0, len(lst), size):
        yield lst[i : i + size]
