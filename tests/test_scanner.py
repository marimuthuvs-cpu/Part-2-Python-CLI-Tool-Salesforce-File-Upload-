"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            test_scanner.py
@Purpose         Tests for the scanner module — folder scanning, Contact ID extraction, and edge cases.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import pytest

from headshot_upload.modules.scanner import HeadshotFile, extract_contact_id, scan_folder
from tests.conftest import CONTACT_ID_15, CONTACT_ID_18_A, CONTACT_ID_18_B

__author__ = "Marimuthu V S"


# ─── Success Scenarios ───────────────────────────────────────────────────────────────────────────────────────

class TestScanFolderSuccess:
    """Tests for successful folder scanning."""

    def test_scan_folder_finds_valid_jpgs(self, sample_folder):
        """Scanning a folder with valid JPEG files returns the expected HeadshotFile objects."""
        results = scan_folder(str(sample_folder))

        assert len(results) == 2, "Should find exactly 2 valid headshot files"
        assert all(isinstance(r, HeadshotFile) for r in results), "All results should be HeadshotFile"

        contact_ids = {r.contact_id for r in results}
        assert CONTACT_ID_18_A in contact_ids, "Should extract Contact ID A"
        assert CONTACT_ID_18_B in contact_ids, "Should extract Contact ID B"

    def test_scan_folder_with_15char_id(self, folder_with_15char_id):
        """Scanning a folder with a 15-char Contact ID filename extracts the ID correctly."""
        results = scan_folder(str(folder_with_15char_id))

        assert len(results) == 1, "Should find exactly 1 valid headshot file"
        assert results[0].contact_id == CONTACT_ID_15, "Should extract the 15-char Contact ID"

    def test_scan_folder_returns_sorted(self, sample_folder):
        """Results should be sorted by filename for deterministic output."""
        results = scan_folder(str(sample_folder))
        filenames = [r.filename for r in results]

        assert filenames == sorted(filenames), "Results should be sorted alphabetically by filename"

    def test_scan_folder_populates_file_attributes(self, sample_folder):
        """Each HeadshotFile should have valid file_path, filename, and contact_id."""
        results = scan_folder(str(sample_folder))

        for r in results:
            assert r.file_path.exists(), "file_path should point to an existing file"
            assert r.filename, "filename should not be empty"
            assert r.contact_id, "contact_id should not be empty"
            assert r.file_size_bytes > 0, "file_size_bytes should be positive"


# ─── Filtering Scenarios ─────────────────────────────────────────────────────────────────────────────────────

class TestScanFolderFiltering:
    """Tests for file filtering — non-JPEG, invalid names, etc."""

    def test_scan_folder_skips_unsupported_formats(self, mixed_folder):
        """Only supported image files (.jpg, .jpeg) should be included — PNG, GIF, and TXT are skipped."""
        results = scan_folder(str(mixed_folder))

        assert len(results) == 2, "Should find 2 valid headshots (JPG + JPEG with valid Contact IDs)"
        contact_ids = {r.contact_id for r in results}
        assert CONTACT_ID_18_A in contact_ids, "Should include the JPG headshot"
        assert CONTACT_ID_18_B in contact_ids, "Should include the JPEG headshot"

    def test_scan_folder_skips_invalid_contact_id(self, mixed_folder):
        """JPEG files without a valid Contact ID in the name should be skipped."""
        results = scan_folder(str(mixed_folder))
        filenames = {r.filename for r in results}

        assert "random_name.jpg" not in filenames, "JPEG without Contact ID should be skipped"

    def test_scan_folder_empty_directory(self, empty_folder):
        """Scanning an empty directory returns an empty list without errors."""
        results = scan_folder(str(empty_folder))
        assert results == [], "Empty folder should return an empty list"


# ─── Failure Scenarios ───────────────────────────────────────────────────────────────────────────────────────

class TestScanFolderErrors:
    """Tests for error handling — missing folder, not a directory, etc."""

    def test_scan_folder_not_found_raises(self):
        """Scanning a non-existent folder should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Folder not found"):
            scan_folder("/nonexistent/path/to/folder")

    def test_scan_folder_not_directory_raises(self, tmp_path):
        """Scanning a file path (not a directory) should raise NotADirectoryError."""
        file_path = tmp_path / "somefile.txt"
        file_path.write_text("not a directory")

        with pytest.raises(NotADirectoryError, match="not a directory"):
            scan_folder(str(file_path))


# ─── Contact ID Extraction ───────────────────────────────────────────────────────────────────────────────────

class TestExtractContactId:
    """Tests for the Contact ID extraction function."""

    def test_extract_18char_id(self):
        """Should extract a valid 18-character Contact ID from the start of the filename."""
        result = extract_contact_id("003AB00000Abc1DEFA_headshot")
        assert result == "003AB00000Abc1DEFA", "Should extract 18-char Contact ID"

    def test_extract_18char_id_no_suffix(self):
        """Should extract an 18-char Contact ID when no suffix is present."""
        result = extract_contact_id("003AB00000Abc1DEFA")
        assert result == "003AB00000Abc1DEFA", "Should extract 18-char ID without suffix"

    def test_extract_15char_id(self):
        """Should extract a valid 15-character Contact ID."""
        result = extract_contact_id("003AB00000Abc12_photo")
        assert result == "003AB00000Abc12", "Should extract 15-char Contact ID"

    def test_extract_15char_id_no_suffix(self):
        """Should extract a 15-char Contact ID when no suffix is present."""
        result = extract_contact_id("003AB00000Abc12")
        assert result == "003AB00000Abc12", "Should extract 15-char ID without suffix"

    def test_extract_invalid_prefix(self):
        """IDs not starting with '003' should return None."""
        result = extract_contact_id("001AB00000Abc1DEF")
        assert result is None, "Account ID prefix 001 should not match"

    def test_extract_too_short(self):
        """IDs shorter than 15 characters should return None."""
        result = extract_contact_id("003AB0000")
        assert result is None, "Too-short ID should return None"

    def test_extract_random_string(self):
        """A random filename with no Contact ID returns None."""
        result = extract_contact_id("headshot_photo_2026")
        assert result is None, "Random string should return None"

    def test_extract_empty_string(self):
        """An empty string returns None."""
        result = extract_contact_id("")
        assert result is None, "Empty string should return None"

    def test_extract_id_with_special_characters(self):
        """Contact ID followed by non-underscore character should not match."""
        result = extract_contact_id("003AB00000Abc1DEFA-headshot")
        assert result is None, "Hyphen after ID should not match — only underscore is valid"
