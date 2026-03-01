"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            scanner.py
@TestClass       test_scanner.py
@Purpose         Scans a folder for headshot image files (JPEG) and extracts Salesforce Contact IDs from filenames.
                 Provides the file-discovery and ID-extraction logic consumed by the uploader module.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

__author__ = "Marimuthu V S"

logger = logging.getLogger(__name__)


# ─── Constants ─────────────────────────────────────────────────────────────────────────────────────────────

# Valid image file extensions (case-insensitive check performed at scan time)
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg"}

# Salesforce Contact ID extraction pattern:
#   - Must start with "003" (standard Contact key prefix)
#   - Followed by exactly 12 more alnum chars (15-char ID) or 15 more (18-char ID)
#   - Immediately followed by an underscore, period, or end-of-string
# The alternation tries the 18-char match first (longer match wins)
CONTACT_ID_PATTERN = re.compile(
    r"^(003[a-zA-Z0-9]{15}|003[a-zA-Z0-9]{12})(?:_|$)"
)


# ─── Data Classes ──────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class HeadshotFile:
    """Represents a scanned headshot file with its associated Salesforce Contact ID."""

    file_path: Path
    filename: str
    contact_id: str

    @property
    def file_size_bytes(self) -> int:
        """Return the file size in bytes."""
        return self.file_path.stat().st_size

    @property
    def file_size_display(self) -> str:
        """Return a human-readable file size string (e.g., '1.2 MB')."""
        size = float(self.file_size_bytes)
        for unit in ("B", "KB", "MB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


# ─── Public Functions ──────────────────────────────────────────────────────────────────────────────────────

def scan_folder(folder_path: str) -> List[HeadshotFile]:
    """Scan a directory for headshot image files (JPEG) whose filenames start with a
    Salesforce Contact ID (15- or 18-char, prefix 003). After the ID, only an underscore
    or end-of-name is accepted. Skips files with unsupported extensions or invalid IDs.

    Args:
        folder_path: Absolute or relative path to the folder containing headshot images.

    Returns:
        Sorted list of HeadshotFile objects for every valid file found.

    Raises:
        FileNotFoundError:  If folder_path does not exist.
        NotADirectoryError: If folder_path is not a directory.
    """
    path = Path(folder_path)

    if not path.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {folder_path}")

    headshots: List[HeadshotFile] = []
    skipped_count = 0

    for file in sorted(path.iterdir()):
        if not file.is_file():
            continue

        # Only process supported image formats (JPEG)
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        # Attempt to extract a Contact ID from the filename
        contact_id = extract_contact_id(file.stem)
        if contact_id is None:
            logger.warning(
                "Skipping file '%s' — unable to extract a valid Contact ID from filename",
                file.name,
            )
            skipped_count += 1
            continue

        headshots.append(
            HeadshotFile(
                file_path=file,
                filename=file.name,
                contact_id=contact_id,
            )
        )

    logger.info(
        "Scan complete — %d valid headshot(s) found, %d file(s) skipped in '%s'",
        len(headshots),
        skipped_count,
        folder_path,
    )
    return headshots


def extract_contact_id(filename_stem: str) -> Optional[str]:
    """Extract a Salesforce Contact ID from a filename stem (name without extension).
    The stem must start with a valid 15- or 18-character Contact ID (prefix 003),
    followed by an underscore or end-of-string.

    Args:
        filename_stem: Filename without extension (e.g., '003AB00000Abc1DEF_headshot').

    Returns:
        Extracted Contact ID string, or None if no valid ID is found.
    """
    if not filename_stem:
        return None

    match = CONTACT_ID_PATTERN.match(filename_stem)
    if not match:
        return None

    return match.group(1)
