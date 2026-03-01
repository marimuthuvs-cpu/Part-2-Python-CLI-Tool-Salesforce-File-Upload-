"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            uploader.py
@TestClass       test_uploader.py
@Purpose         Business-logic orchestration layer. Coordinates file encoding, ContentVersion creation,
                 ContentDocumentId lookup, and ContentDocumentLink creation into a single upload workflow.
                 Designed to be reusable outside the CLI — no Click imports, no console output.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from headshot_upload.config import UPLOAD_BATCH_SIZE
from headshot_upload.modules.auth import SalesforceSession
from headshot_upload.modules.encoder import EncodingError, encode_file_to_base64
from headshot_upload.modules.scanner import HeadshotFile
from headshot_upload.modules.salesforce_api import (
    ContentDocumentLinkData,
    HeadshotPayload,
    create_content_document_links,
    create_content_versions,
    query_content_document_ids,
)

__author__ = "Marimuthu V S"

logger = logging.getLogger(__name__)


# ─── Data Classes ──────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class UploadResult:
    """Tracks the outcome of uploading a single headshot file to Salesforce."""

    contact_id: str
    filename: str
    success: bool
    content_version_id: Optional[str] = None
    content_document_id: Optional[str] = None
    content_document_link_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class UploadReport:
    """Summary report for a complete upload session."""

    total: int
    successful: int
    failed: int
    results: List[UploadResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate the success rate as a percentage (0.0–100.0)."""
        return (self.successful / self.total * 100) if self.total > 0 else 0.0


# ─── Public Functions ──────────────────────────────────────────────────────────────────────────────────────

def upload_headshots(
    session: SalesforceSession,
    headshot_files: List[HeadshotFile],
    batch_size: int = UPLOAD_BATCH_SIZE,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> UploadReport:
    """Upload headshot images to Salesforce and link them to their respective Contact records.
    Executes a three-phase process: encode & create ContentVersions, query ContentDocumentIds,
    and create ContentDocumentLinks. Uses allOrNone: false for partial success support.

    Args:
        session:           Authenticated SalesforceSession.
        headshot_files:    List of HeadshotFile objects from the scanner.
        batch_size:        Number of headshots per outer batch (controls memory).
        progress_callback: Optional callback with count of items processed.

    Returns:
        UploadReport summarising overall results and per-file outcomes.
    """
    if not headshot_files:
        logger.info("No headshot files to upload — returning empty report")
        return UploadReport(total=0, successful=0, failed=0)

    all_results: List[UploadResult] = []

    for batch in _chunks(headshot_files, batch_size):
        batch_results = _process_batch(session, batch)
        all_results.extend(batch_results)

        if progress_callback:
            progress_callback(len(batch))

    successful = sum(1 for r in all_results if r.success)
    failed = len(all_results) - successful

    logger.info(
        "Upload session complete — %d total, %d successful, %d failed (%.1f%%)",
        len(all_results),
        successful,
        failed,
        (successful / len(all_results) * 100) if all_results else 0,
    )

    return UploadReport(
        total=len(all_results),
        successful=successful,
        failed=failed,
        results=all_results,
    )


def generate_dry_run_report(headshot_files: List[HeadshotFile]) -> List[Dict[str, str]]:
    """Generate a preview of what would happen during an actual upload — no API calls made.

    Args:
        headshot_files: List of HeadshotFile objects from the scanner.

    Returns:
        List of dicts describing the planned action for each headshot file.
    """
    report: List[Dict[str, str]] = []

    for hf in headshot_files:
        report.append({
            "filename": hf.filename,
            "contact_id": hf.contact_id,
            "file_size": hf.file_size_display,
            "action": "Upload ContentVersion → Link to Contact via ContentDocumentLink",
        })

    return report


# ─── Private Functions ─────────────────────────────────────────────────────────────────────────────────────

def _process_batch(
    session: SalesforceSession,
    batch: List[HeadshotFile],
) -> List[UploadResult]:
    """Process a single batch of headshots through all three upload phases.

    Args:
        session: Authenticated SalesforceSession.
        batch:   List of HeadshotFile objects to process.

    Returns:
        List of UploadResult — one per file in the batch.
    """
    results: List[UploadResult] = []

    # ─── Phase 1: Encode files and create ContentVersions ──────────────────────────────────────────────

    payloads: List[HeadshotPayload] = []
    # Maps contact_id → filename for results tracking
    file_map: Dict[str, str] = {}

    for hf in batch:
        try:
            base64_data = encode_file_to_base64(hf.file_path)
        except EncodingError as exc:
            logger.error("Encoding failed for '%s': %s", hf.filename, exc)
            results.append(UploadResult(
                contact_id=hf.contact_id,
                filename=hf.filename,
                success=False,
                error=f"Encoding failed: {exc}",
            ))
            continue

        payloads.append(HeadshotPayload(
            contact_id=hf.contact_id,
            filename=hf.filename,
            title=f"Headshot — {hf.contact_id}",
            base64_data=base64_data,
        ))
        file_map[hf.contact_id] = hf.filename

    if not payloads:
        return results

    cv_results = create_content_versions(session, payloads)

    # Collect successful CV IDs and track failures
    cv_id_to_contact: Dict[str, str] = {}

    for cvr in cv_results:
        if not cvr.success:
            results.append(UploadResult(
                contact_id=cvr.contact_id,
                filename=file_map.get(cvr.contact_id, "unknown"),
                success=False,
                error=f"ContentVersion creation failed: {cvr.error}",
            ))
        else:
            cv_id_to_contact[cvr.content_version_id] = cvr.contact_id

    if not cv_id_to_contact:
        return results

    # ─── Phase 2: Query ContentDocumentIds ─────────────────────────────────────────────────────────────

    cv_to_doc = query_content_document_ids(session, list(cv_id_to_contact.keys()))

    # ─── Phase 3: Create ContentDocumentLinks ──────────────────────────────────────────────────────────

    cdl_data: List[ContentDocumentLinkData] = []
    # Track mappings for result assembly: contact_id → { cv_id, doc_id }
    link_context: Dict[str, Dict[str, str]] = {}

    for cv_id, contact_id in cv_id_to_contact.items():
        doc_id = cv_to_doc.get(cv_id)
        if not doc_id:
            logger.error(
                "ContentDocumentId not found for ContentVersion %s (Contact %s)",
                cv_id,
                contact_id,
            )
            results.append(UploadResult(
                contact_id=contact_id,
                filename=file_map.get(contact_id, "unknown"),
                success=False,
                content_version_id=cv_id,
                error="ContentDocumentId not found after ContentVersion creation",
            ))
            continue

        cdl_data.append(ContentDocumentLinkData(
            content_document_id=doc_id,
            linked_entity_id=contact_id,
        ))
        link_context[contact_id] = {
            "content_version_id": cv_id,
            "content_document_id": doc_id,
        }

    if not cdl_data:
        return results

    cdl_results = create_content_document_links(session, cdl_data)

    for cdl_r in cdl_results:
        ctx = link_context.get(cdl_r.contact_id, {})
        results.append(UploadResult(
            contact_id=cdl_r.contact_id,
            filename=file_map.get(cdl_r.contact_id, "unknown"),
            success=cdl_r.success,
            content_version_id=ctx.get("content_version_id"),
            content_document_id=ctx.get("content_document_id"),
            content_document_link_id=cdl_r.content_document_link_id if cdl_r.success else None,
            error=f"ContentDocumentLink creation failed: {cdl_r.error}" if not cdl_r.success else None,
        ))

    return results


def _chunks(lst: list, size: int):
    """Yield successive chunks of the given size from lst.

    Args:
        lst:  The list to split.
        size: Maximum chunk size.
    """
    for i in range(0, len(lst), size):
        yield lst[i : i + size]
