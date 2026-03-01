"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            auth.py
@TestClass       test_auth.py
@Purpose         Salesforce OAuth authentication using Client Credentials or Username-Password flow.
                 Client Credentials is preferred; Username-Password is used as a fallback.
                 Returns an authenticated session with access token and instance URL for API calls.
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import logging
from dataclasses import dataclass
from typing import Dict

import requests

from headshot_upload.config import SalesforceConfig

__author__ = "Marimuthu V S"

logger = logging.getLogger(__name__)


# ─── Exceptions ────────────────────────────────────────────────────────────────────────────────────────────

class AuthenticationError(Exception):
    """Raised when Salesforce authentication fails."""
    pass


# ─── Data Classes ──────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class SalesforceSession:
    """Holds an authenticated Salesforce session with the details needed for REST API calls."""

    access_token: str
    instance_url: str
    api_version: str

    @property
    def base_url(self) -> str:
        """Build the versioned REST API base URL."""
        return f"{self.instance_url}/services/data/v{self.api_version}"

    @property
    def headers(self) -> Dict[str, str]:
        """Build standard API request headers with Bearer authentication."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }


# ─── Public Functions ──────────────────────────────────────────────────────────────────────────────────────

def authenticate(config: SalesforceConfig) -> SalesforceSession:
    """Authenticate with Salesforce using the best available OAuth flow.
    Tries Client Credentials first (preferred for server-to-server), then falls back
    to Username-Password if Client Credentials config is not available.

    Args:
        config: SalesforceConfig instance loaded from environment variables.

    Returns:
        Authenticated SalesforceSession ready for API calls.

    Raises:
        AuthenticationError: If no valid authentication method is available.
    """
    # Prefer Client Credentials flow (no user context required)
    if config.is_client_credentials:
        logger.info("Attempting Client Credentials authentication flow")
        return _authenticate_client_credentials(config)

    # Fallback to Username-Password flow
    if config.is_username_password:
        logger.info("Attempting Username-Password authentication flow")
        return _authenticate_username_password(config)

    raise AuthenticationError(
        "No valid authentication credentials provided. "
        "Configure SF_CLIENT_ID + SF_CLIENT_SECRET (Client Credentials) or "
        "SF_CLIENT_ID + SF_CLIENT_SECRET + SF_USERNAME + SF_PASSWORD (Username-Password) "
        "as environment variables."
    )


# ─── Private Functions ─────────────────────────────────────────────────────────────────────────────────────

def _authenticate_client_credentials(config: SalesforceConfig) -> SalesforceSession:
    """Authenticate using the OAuth 2.0 Client Credentials flow. Preferred for server-to-server
    integrations. Requires a Connected App configured for Client Credentials grant type.

    Args:
        config: Configuration with client_id and client_secret.

    Returns:
        Authenticated SalesforceSession.
    """
    token_url = f"{config.login_url}/services/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": config.client_id,
        "client_secret": config.client_secret,
    }

    return _request_token(token_url, payload, config.api_version, "Client Credentials")


def _authenticate_username_password(config: SalesforceConfig) -> SalesforceSession:
    """Authenticate using the OAuth 2.0 Username-Password flow. Used when Client Credentials
    is not available. Requires a Connected App plus Salesforce username/password.
    Security token is appended to the password if provided.

    Args:
        config: Configuration with client_id, client_secret, username, password, and optional security_token.

    Returns:
        Authenticated SalesforceSession.
    """
    token_url = f"{config.login_url}/services/oauth2/token"

    # Salesforce expects password + security_token concatenated
    password = config.password
    if config.security_token:
        password += config.security_token

    payload = {
        "grant_type": "password",
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "username": config.username,
        "password": password,
    }

    return _request_token(token_url, payload, config.api_version, "Username-Password")


def _request_token(
    token_url: str,
    payload: dict,
    api_version: str,
    flow_name: str,
) -> SalesforceSession:
    """Send a token request to the Salesforce OAuth endpoint and parse the response.

    Args:
        token_url:   Full URL of the /services/oauth2/token endpoint.
        payload:     Form-encoded body parameters for the token request.
        api_version: Salesforce API version string (e.g., "65.0").
        flow_name:   Human-readable name of the OAuth flow for logging.

    Returns:
        Authenticated SalesforceSession.
    """
    try:
        response = requests.post(token_url, data=payload, timeout=30)
        response.raise_for_status()
        data = response.json()

        session = SalesforceSession(
            access_token=data["access_token"],
            instance_url=data["instance_url"],
            api_version=api_version,
        )
        logger.info(
            "%s authentication successful — instance: %s",
            flow_name,
            session.instance_url,
        )
        return session

    except requests.exceptions.RequestException as exc:
        logger.error("%s authentication failed: %s", flow_name, exc)
        raise AuthenticationError(f"{flow_name} flow failed: {exc}") from exc
    except (KeyError, ValueError) as exc:
        logger.error("Invalid authentication response from Salesforce: %s", exc)
        raise AuthenticationError(
            f"Invalid response from Salesforce during {flow_name} flow: {exc}"
        ) from exc
