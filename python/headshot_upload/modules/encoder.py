"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            encoder.py
@TestClass       test_encoder.py
@Purpose         Base64-encodes image files (JPEG) for inclusion in Salesforce ContentVersion API payloads.
                 Provides a thin, reusable encoding layer consumed by the uploader module.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import base64
import logging
from pathlib import Path

__author__ = "Marimuthu V S"

logger = logging.getLogger(__name__)


# ─── Exceptions ────────────────────────────────────────────────────────────────────────────────────────────

class EncodingError(Exception):
    """Raised when a file cannot be read or base64-encoded."""
    pass


# ─── Public Functions ──────────────────────────────────────────────────────────────────────────────────────

def encode_file_to_base64(file_path: Path) -> str:
    """Read a file from disk and return its contents as a base64-encoded UTF-8 string.
    Suitable for the VersionData field on Salesforce ContentVersion records.

    Args:
        file_path: Absolute path to the file to encode.

    Returns:
        Base64-encoded string of the file's binary content.

    Raises:
        EncodingError: If the file does not exist, cannot be read, or encoding fails.
    """
    if not file_path.exists():
        raise EncodingError(f"File not found: {file_path}")

    if not file_path.is_file():
        raise EncodingError(f"Path is not a file: {file_path}")

    try:
        raw_bytes = file_path.read_bytes()
        encoded = base64.b64encode(raw_bytes).decode("utf-8")

        logger.debug(
            "Encoded '%s' — %d bytes → %d base64 chars",
            file_path.name,
            len(raw_bytes),
            len(encoded),
        )
        return encoded

    except OSError as exc:
        raise EncodingError(f"Failed to read file '{file_path}': {exc}") from exc
    except Exception as exc:
        raise EncodingError(f"Failed to encode file '{file_path}': {exc}") from exc
