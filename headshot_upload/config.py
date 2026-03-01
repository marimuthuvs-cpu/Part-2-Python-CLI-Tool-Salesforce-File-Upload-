"""
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@Name            config.py
@TestClass       test_config.py
@Purpose         Centralised configuration management. Loads Salesforce credentials and settings from
                 environment variables with support for multiple environments (prod, sandbox).
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@History
VERSION     AUTHOR              DATE                DETAIL DESCRIPTION
1.0         Marimuthu V S       February 25, 2026   Initial Development
──────────────────────────────────────────────────────────────────────────────────────────────────────────────
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

__author__ = "Marimuthu V S"

logger = logging.getLogger(__name__)


# ─── Constants ─────────────────────────────────────────────────────────────────────────────────────────────

DEFAULT_API_VERSION = "65.0"
DEFAULT_LOGIN_URL = "https://login.salesforce.com"
SANDBOX_LOGIN_URL = "https://test.salesforce.com"

# Composite API supports up to 25 sub-requests per call
COMPOSITE_MAX_SUBREQUESTS = 25
# Smaller batch for ContentVersion (large base64 payloads) to avoid exceeding request body limits
CV_COMPOSITE_BATCH_SIZE = 10
# ContentDocumentLink payloads are lightweight — use full composite limit
CDL_COMPOSITE_BATCH_SIZE = 25
# Outer processing batch — controls memory usage for large folders
UPLOAD_BATCH_SIZE = 25
# SOQL IN clause batch size
QUERY_BATCH_SIZE = 200


# ─── Exceptions ────────────────────────────────────────────────────────────────────────────────────────────

class ConfigurationError(Exception):
    """Raised when required configuration is missing or invalid."""
    pass


# ─── Data Class ────────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class SalesforceConfig:
    """Holds Salesforce connection configuration loaded from environment variables."""

    login_url: str
    client_id: str = ""
    client_secret: str = ""
    username: str = ""
    password: str = ""
    security_token: Optional[str] = None
    api_version: str = DEFAULT_API_VERSION

    @property
    def is_client_credentials(self) -> bool:
        """Check if Client Credentials flow can be used (client_id + client_secret present)."""
        return bool(self.client_id and self.client_secret)

    @property
    def is_username_password(self) -> bool:
        """Check if Username-Password flow can be used (client_id + client_secret + username + password)."""
        return bool(self.client_id and self.client_secret and self.username and self.password)


# ─── Configuration Loader ──────────────────────────────────────────────────────────────────────────────────

def load_config(environment: str = "prod") -> SalesforceConfig:
    """Load Salesforce configuration from environment variables. Resolves login URL based on
    target environment. SF_LOGIN_URL env var overrides the environment-based default when set.

    Args:
        environment: Target environment — "prod" or "sandbox". Defaults to "prod".

    Returns:
        Fully populated SalesforceConfig instance.

    Raises:
        ConfigurationError: If no valid authentication credentials are found.
    """
    # Resolve login URL: explicit override > environment-based default
    login_url = os.environ.get(
        "SF_LOGIN_URL",
        SANDBOX_LOGIN_URL if environment == "sandbox" else DEFAULT_LOGIN_URL,
    )

    config = SalesforceConfig(
        login_url=login_url,
        client_id=os.environ.get("SF_CLIENT_ID", ""),
        client_secret=os.environ.get("SF_CLIENT_SECRET", ""),
        username=os.environ.get("SF_USERNAME", ""),
        password=os.environ.get("SF_PASSWORD", ""),
        security_token=os.environ.get("SF_SECURITY_TOKEN") or None,
        api_version=os.environ.get("SF_API_VERSION", DEFAULT_API_VERSION),
    )

    # Validate — at least one authentication method must be available
    if not config.is_client_credentials and not config.is_username_password:
        raise ConfigurationError(
            "Missing authentication credentials. Provide either "
            "SF_CLIENT_ID + SF_CLIENT_SECRET (Client Credentials flow) or "
            "SF_CLIENT_ID + SF_CLIENT_SECRET + SF_USERNAME + SF_PASSWORD (Username-Password flow) "
            "as environment variables."
        )

    logger.info(
        "Configuration loaded — environment: %s, login_url: %s",
        environment,
        login_url,
    )
    return config
