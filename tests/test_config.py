"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            test_config.py
@Purpose         Tests for the config module — environment variable loading, authentication method
                 detection (Client Credentials and Username-Password), validation, and edge cases.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 26, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import os
from unittest.mock import patch

import pytest

from headshot_upload.config import (
    DEFAULT_API_VERSION,
    DEFAULT_LOGIN_URL,
    SANDBOX_LOGIN_URL,
    ConfigurationError,
    SalesforceConfig,
    load_config,
)

__author__ = "Marimuthu V S"


# ─── SalesforceConfig Property Tests ────────────────────────────────────────────────────────────────────────

class TestSalesforceConfigProperties:
    """Tests for the SalesforceConfig authentication-method detection properties."""

    def test_is_client_credentials_true(self):
        """is_client_credentials returns True when client_id and client_secret are set."""
        config = SalesforceConfig(
            login_url=DEFAULT_LOGIN_URL,
            client_id="my_client_id",
            client_secret="my_client_secret",
        )
        assert config.is_client_credentials is True

    def test_is_client_credentials_false(self):
        """is_client_credentials returns False when client_id is missing."""
        config = SalesforceConfig(
            login_url=DEFAULT_LOGIN_URL,
            client_secret="my_client_secret",
        )
        assert config.is_client_credentials is False

    def test_is_username_password_true(self):
        """is_username_password returns True when client_id, client_secret, username, and password are set."""
        config = SalesforceConfig(
            login_url=DEFAULT_LOGIN_URL,
            client_id="my_client_id",
            client_secret="my_client_secret",
            username="user@example.com",
            password="password123",
        )
        assert config.is_username_password is True

    def test_is_username_password_false_missing_username(self):
        """is_username_password returns False when username is missing."""
        config = SalesforceConfig(
            login_url=DEFAULT_LOGIN_URL,
            client_id="my_client_id",
            client_secret="my_client_secret",
            password="password123",
        )
        assert config.is_username_password is False

    def test_is_username_password_false_missing_password(self):
        """is_username_password returns False when password is missing."""
        config = SalesforceConfig(
            login_url=DEFAULT_LOGIN_URL,
            client_id="my_client_id",
            client_secret="my_client_secret",
            username="user@example.com",
        )
        assert config.is_username_password is False


# ─── load_config Tests ──────────────────────────────────────────────────────────────────────────────────────

class TestLoadConfig:
    """Tests for the load_config function."""


    @patch.dict(os.environ, {
        "SF_CLIENT_ID": "test_client_id",
        "SF_CLIENT_SECRET": "test_client_secret",
    }, clear=True)
    def test_load_config_client_credentials(self):
        """load_config with client credentials env vars creates a valid config."""
        config = load_config()
        assert config.client_id == "test_client_id"
        assert config.client_secret == "test_client_secret"
        assert config.is_client_credentials is True
        assert config.login_url == DEFAULT_LOGIN_URL


    @patch.dict(os.environ, {
        "SF_CLIENT_ID": "test_client_id",
        "SF_CLIENT_SECRET": "test_client_secret",
        "SF_USERNAME": "user@example.com",
        "SF_PASSWORD": "pass123",
        "SF_SECURITY_TOKEN": "tok456",
    }, clear=True)
    def test_load_config_username_password(self):
        """load_config with username-password env vars creates a valid config."""
        config = load_config()
        assert config.username == "user@example.com"
        assert config.password == "pass123"
        assert config.security_token == "tok456"
        assert config.is_username_password is True


    @patch.dict(os.environ, {
        "SF_CLIENT_ID": "test_client_id",
        "SF_CLIENT_SECRET": "test_client_secret",
    }, clear=True)
    def test_load_config_sandbox_environment(self):
        """load_config with environment='sandbox' uses the sandbox login URL."""
        config = load_config(environment="sandbox")
        assert config.login_url == SANDBOX_LOGIN_URL


    @patch.dict(os.environ, {
        "SF_CLIENT_ID": "test_client_id",
        "SF_CLIENT_SECRET": "test_client_secret",
        "SF_LOGIN_URL": "https://custom.salesforce.com",
    }, clear=True)
    def test_load_config_custom_login_url(self):
        """Explicit SF_LOGIN_URL overrides the environment-based default."""
        config = load_config()
        assert config.login_url == "https://custom.salesforce.com"


    @patch.dict(os.environ, {
        "SF_CLIENT_ID": "cid",
        "SF_CLIENT_SECRET": "csecret",
        "SF_API_VERSION": "62.0",
    }, clear=True)
    def test_load_config_custom_api_version(self):
        """Custom SF_API_VERSION is loaded from environment."""
        config = load_config()
        assert config.api_version == "62.0"


    @patch.dict(os.environ, {
        "SF_CLIENT_ID": "cid",
        "SF_CLIENT_SECRET": "csecret",
    }, clear=True)
    def test_load_config_default_api_version(self):
        """API version defaults to DEFAULT_API_VERSION when not set."""
        config = load_config()
        assert config.api_version == DEFAULT_API_VERSION


    @patch.dict(os.environ, {}, clear=True)
    def test_load_config_no_credentials_raises(self):
        """load_config with no credentials at all raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Missing authentication credentials"):
            load_config()


    @patch.dict(os.environ, {
        "SF_USERNAME": "user@example.com",
        "SF_PASSWORD": "pass123",
    }, clear=True)
    def test_load_config_up_without_client_creds_raises(self):
        """load_config with username/password but no client_id/secret raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Missing authentication credentials"):
            load_config()
