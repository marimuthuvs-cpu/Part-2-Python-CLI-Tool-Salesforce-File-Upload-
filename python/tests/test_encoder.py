"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            test_encoder.py
@Purpose         Tests for the encoder module — base64 encoding of image files, error handling.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import base64

import pytest

from headshot_upload.modules.encoder import EncodingError, encode_file_to_base64
from tests.conftest import MINIMAL_JPEG_BYTES

__author__ = "Marimuthu V S"


# ─── Success Scenarios ───────────────────────────────────────────────────────────────────────────────────────

class TestEncodeSuccess:
    """Tests for successful file encoding."""

    def test_encode_file_returns_valid_base64(self, tmp_path):
        """Encoding a file should return a valid base64 string that decodes back to the original bytes."""
        file_path = tmp_path / "test.jpg"
        file_path.write_bytes(MINIMAL_JPEG_BYTES)

        result = encode_file_to_base64(file_path)

        assert isinstance(result, str), "Result should be a string"
        decoded = base64.b64decode(result)
        assert decoded == MINIMAL_JPEG_BYTES, "Decoded base64 should match original bytes"

    def test_encode_file_is_utf8(self, tmp_path):
        """The base64 output should be a valid UTF-8 string (safe for JSON payloads)."""
        file_path = tmp_path / "test.jpg"
        file_path.write_bytes(MINIMAL_JPEG_BYTES)

        result = encode_file_to_base64(file_path)

        # This should not raise — proving the string is valid UTF-8
        result.encode("utf-8")

    def test_encode_empty_file(self, tmp_path):
        """Encoding an empty file should return an empty base64 string."""
        file_path = tmp_path / "empty.jpg"
        file_path.write_bytes(b"")

        result = encode_file_to_base64(file_path)
        assert result == "", "Empty file should produce empty base64 string"


# ─── Failure Scenarios ───────────────────────────────────────────────────────────────────────────────────────

class TestEncodeErrors:
    """Tests for encoding error handling."""

    def test_encode_file_not_found_raises(self, tmp_path):
        """Encoding a non-existent file should raise EncodingError."""
        fake_path = tmp_path / "nonexistent.jpg"

        with pytest.raises(EncodingError, match="File not found"):
            encode_file_to_base64(fake_path)

    def test_encode_directory_raises(self, tmp_path):
        """Encoding a directory path should raise EncodingError."""
        with pytest.raises(EncodingError, match="not a file"):
            encode_file_to_base64(tmp_path)
