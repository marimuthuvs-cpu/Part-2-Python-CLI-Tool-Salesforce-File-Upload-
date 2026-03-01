"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            conftest.py
@Purpose         Shared pytest fixtures for the Headshot Upload test suite. Provides reusable test data
                 including temporary folders with sample image files, mock configurations, and mock sessions.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import pytest

from headshot_upload.config import SalesforceConfig
from headshot_upload.modules.auth import SalesforceSession

__author__ = "Marimuthu V S"


# ─── Sample Contact IDs ───────────────────────────────────────────────────────────────────────────────────

CONTACT_ID_18_A = "003AB00000Abc1DEFA"
CONTACT_ID_18_B = "003CD00000Xyz9GHIA"
CONTACT_ID_15 = "003AB00000Abc12"

# Minimal JPEG file header (SOI + APP0 marker + padding) — not a valid image but sufficient for tests
MINIMAL_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100



# ─── Fixtures — Temporary Folders ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_folder(tmp_path):
    """Create a temp folder with two valid headshot JPEG files."""
    (tmp_path / f"{CONTACT_ID_18_A}_headshot.jpg").write_bytes(MINIMAL_JPEG_BYTES)
    (tmp_path / f"{CONTACT_ID_18_B}.jpeg").write_bytes(MINIMAL_JPEG_BYTES)
    return tmp_path


@pytest.fixture
def mixed_folder(tmp_path):
    """Create a temp folder with a mix of valid and invalid files (JPEG, GIF, TXT, PNG)."""
    (tmp_path / f"{CONTACT_ID_18_A}.jpg").write_bytes(MINIMAL_JPEG_BYTES)
    (tmp_path / f"{CONTACT_ID_18_B}.jpeg").write_bytes(MINIMAL_JPEG_BYTES)
    (tmp_path / "random_name.jpg").write_bytes(MINIMAL_JPEG_BYTES)
    (tmp_path / "003AB00000Abc1DEFA.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    (tmp_path / "not_an_image.gif").write_bytes(b"GIF89a" + b"\x00" * 50)
    (tmp_path / "notes.txt").write_text("not an image")
    return tmp_path


@pytest.fixture
def empty_folder(tmp_path):
    """Create an empty temporary folder."""
    return tmp_path


@pytest.fixture
def folder_with_15char_id(tmp_path):
    """Create a temp folder with a JPEG named with a 15-char Contact ID."""
    (tmp_path / f"{CONTACT_ID_15}_photo.jpg").write_bytes(MINIMAL_JPEG_BYTES)
    return tmp_path


# ─── Fixtures — Configuration ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_config():
    """Create a test SalesforceConfig with Client Credentials."""
    return SalesforceConfig(
        login_url="https://test.salesforce.com",
        client_id="test_client_id_xxx",
        client_secret="test_client_secret_xxx",
        api_version="65.0",
    )


# ─── Fixtures — Session ───────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_session():
    """Create a test SalesforceSession with dummy credentials."""
    return SalesforceSession(
        access_token="test_access_token_xxx",
        instance_url="https://test.my.salesforce.com",
        api_version="65.0",
    )
