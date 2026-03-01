"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            test_auth.py
@Purpose         Tests for the auth module — OAuth 2.0 Client Credentials and Username-Password
                 authentication flows including success, failure, and edge cases.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 26, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import pytest
import requests
import responses

from headshot_upload.config import SalesforceConfig
from headshot_upload.modules.auth import (
    AuthenticationError,
    SalesforceSession,
    authenticate,
)

__author__ = "Marimuthu V S"


# ─── SalesforceSession Tests ────────────────────────────────────────────────────────────────────────────────

class TestSalesforceSession:
    """Tests for the SalesforceSession data class."""

    def test_base_url(self):
        """base_url should combine instance_url and api_version into a REST API base URL."""
        session = SalesforceSession(
            access_token="token_xxx",
            instance_url="https://test.my.salesforce.com",
            api_version="65.0",
        )
        assert session.base_url == "https://test.my.salesforce.com/services/data/v65.0"

    def test_headers_contain_bearer_token(self):
        """headers should include a Bearer Authorization header."""
        session = SalesforceSession(
            access_token="token_xxx",
            instance_url="https://test.my.salesforce.com",
            api_version="65.0",
        )
        headers = session.headers
        assert headers["Authorization"] == "Bearer token_xxx"
        assert headers["Content-Type"] == "application/json"


# ─── Client Credentials Flow ─────────────────────────────────────────────────────────────────────────────────

class TestClientCredentialsAuth:
    """Tests for the OAuth 2.0 Client Credentials authentication flow."""

    @responses.activate
    def test_client_credentials_success(self, mock_config):
        """Successful Client Credentials flow returns a valid session."""
        responses.add(
            responses.POST,
            f"{mock_config.login_url}/services/oauth2/token",
            json={
                "access_token": "new_access_token_xxx",
                "instance_url": "https://my-org.my.salesforce.com",
                "token_type": "Bearer",
            },
            status=200,
        )

        session = authenticate(mock_config)

        assert isinstance(session, SalesforceSession)
        assert session.access_token == "new_access_token_xxx"
        assert session.instance_url == "https://my-org.my.salesforce.com"

        # Verify the correct grant_type was sent
        request_body = responses.calls[0].request.body
        assert "grant_type=client_credentials" in request_body
        assert f"client_id={mock_config.client_id}" in request_body
        assert f"client_secret={mock_config.client_secret}" in request_body

    @responses.activate
    def test_client_credentials_invalid_credentials(self, mock_config):
        """Invalid client credentials should raise AuthenticationError."""
        responses.add(
            responses.POST,
            f"{mock_config.login_url}/services/oauth2/token",
            json={"error": "invalid_client", "error_description": "Invalid client credentials"},
            status=400,
        )

        with pytest.raises(AuthenticationError, match="Client Credentials flow failed"):
            authenticate(mock_config)


# ─── Username-Password Flow ─────────────────────────────────────────────────────────────────────────────────

class TestUsernamePasswordAuth:
    """Tests for the OAuth 2.0 Username-Password authentication flow."""

    @responses.activate
    def test_username_password_success(self):
        """Successful Username-Password flow returns a valid session."""
        config = SalesforceConfig(
            login_url="https://login.salesforce.com",
            client_id="up_client_id",
            client_secret="up_client_secret",
            username="user@example.com",
            password="pass123",
        )

        responses.add(
            responses.POST,
            "https://login.salesforce.com/services/oauth2/token",
            json={
                "access_token": "up_access_token_xxx",
                "instance_url": "https://up-org.my.salesforce.com",
                "token_type": "Bearer",
            },
            status=200,
        )

        from headshot_upload.modules.auth import _authenticate_username_password
        session = _authenticate_username_password(config)

        assert isinstance(session, SalesforceSession)
        assert session.access_token == "up_access_token_xxx"
        assert session.instance_url == "https://up-org.my.salesforce.com"

        # Verify grant_type and credentials were sent
        request_body = responses.calls[0].request.body
        assert "grant_type=password" in request_body
        assert "username=user%40example.com" in request_body

    @responses.activate
    def test_username_password_with_security_token(self):
        """Security token is appended to the password when provided."""
        config = SalesforceConfig(
            login_url="https://login.salesforce.com",
            client_id="up_client_id",
            client_secret="up_client_secret",
            username="user@example.com",
            password="pass123",
            security_token="sectoken789",
        )

        responses.add(
            responses.POST,
            "https://login.salesforce.com/services/oauth2/token",
            json={
                "access_token": "token_with_sec",
                "instance_url": "https://sec-org.my.salesforce.com",
                "token_type": "Bearer",
            },
            status=200,
        )

        from headshot_upload.modules.auth import _authenticate_username_password
        session = _authenticate_username_password(config)

        assert session.access_token == "token_with_sec"

        # Verify password + security_token concatenated in the request
        request_body = responses.calls[0].request.body
        assert "password=pass123sectoken789" in request_body

    @responses.activate
    def test_username_password_invalid_credentials(self):
        """Invalid username/password should raise AuthenticationError."""
        config = SalesforceConfig(
            login_url="https://login.salesforce.com",
            client_id="up_client_id",
            client_secret="up_client_secret",
            username="bad@example.com",
            password="wrong",
        )

        responses.add(
            responses.POST,
            "https://login.salesforce.com/services/oauth2/token",
            json={"error": "invalid_grant", "error_description": "Authentication failure"},
            status=400,
        )

        from headshot_upload.modules.auth import _authenticate_username_password
        with pytest.raises(AuthenticationError, match="Username-Password flow failed"):
            _authenticate_username_password(config)


# ─── No Credentials ──────────────────────────────────────────────────────────────────────────────────────────

class TestNoCredentials:
    """Tests for when no valid authentication method is available."""

    def test_no_credentials_raises(self):
        """authenticate should raise AuthenticationError when no method is available."""
        config = SalesforceConfig(
            login_url="https://login.salesforce.com",
        )

        with pytest.raises(AuthenticationError, match="No valid authentication credentials"):
            authenticate(config)

    def test_username_only_no_client_creds_raises(self):
        """authenticate with username/password but no client creds should raise AuthenticationError."""
        config = SalesforceConfig(
            login_url="https://login.salesforce.com",
            username="user@example.com",
            password="pass123",
        )

        with pytest.raises(AuthenticationError, match="No valid authentication credentials"):
            authenticate(config)


# ─── Network Errors ──────────────────────────────────────────────────────────────────────────────────────────

class TestAuthNetworkErrors:
    """Tests for network-level authentication failures."""

    @responses.activate
    def test_network_error_raises_auth_error(self, mock_config):
        """A network error during authentication should raise AuthenticationError."""
        responses.add(
            responses.POST,
            f"{mock_config.login_url}/services/oauth2/token",
            body=requests.exceptions.ConnectionError("Connection refused"),
        )

        with pytest.raises(AuthenticationError, match="Client Credentials flow failed"):
            authenticate(mock_config)

    @responses.activate
    def test_malformed_response_raises_auth_error(self, mock_config):
        """A response without access_token should raise AuthenticationError."""
        responses.add(
            responses.POST,
            f"{mock_config.login_url}/services/oauth2/token",
            json={"unexpected_field": "no_token_here"},
            status=200,
        )

        with pytest.raises(AuthenticationError, match="Invalid response"):
            authenticate(mock_config)
