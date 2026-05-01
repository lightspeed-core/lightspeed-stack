"""Red Hat Identity header authentication for FastAPI endpoints.

This module provides authentication via the x-rh-identity header, supporting both
User and System identity types with optional entitlement validation.
"""

import base64
import json
import time
from typing import Any, Final, Optional

from fastapi import HTTPException, Request

from authentication.interface import NO_AUTH_TUPLE, AuthInterface, AuthTuple
from authentication.utils import record_auth_metrics
from configuration import configuration
from constants import (
    AUTH_MOD_RH_IDENTITY,
    DEFAULT_RH_IDENTITY_MAX_HEADER_SIZE,
    DEFAULT_VIRTUAL_PATH,
    NO_USER_TOKEN,
)
from log import get_logger

logger = get_logger(__name__)

RH_INSIGHTS_REQUEST_ID_HEADER = "x-rh-insights-request-id"
REQUEST_ID_HEADER = "x-request-id"

HEALTH_PROBE_SKIP_PATHS: Final[frozenset[str]] = frozenset({"/readiness", "/liveness"})
METRICS_SKIP_PATH: Final[str] = "/metrics"


def _get_request_id(request: Request) -> str:
    """Return the inbound request identifier available during authentication."""
    return request.headers.get(RH_INSIGHTS_REQUEST_ID_HEADER) or request.headers.get(
        REQUEST_ID_HEADER,
        "",
    )


def _record_rh_identity_auth(result: str, reason: str, start_time: float) -> None:
    """Record RH Identity authentication metrics with bounded labels."""
    record_auth_metrics(AUTH_MOD_RH_IDENTITY, result, reason, start_time)


def _normalized_request_path(request: Request) -> str:
    """Return a canonical request path for exact skip-path comparisons."""
    return request.url.path.rstrip("/") or "/"


def _get_auth_skip_tuple(request: Request, start_time: float) -> Optional[AuthTuple]:
    """Return an auth tuple for configured RH Identity skip paths."""
    request_path = _normalized_request_path(request)
    if request_path in HEALTH_PROBE_SKIP_PATHS:
        if configuration.authentication_configuration.skip_for_health_probes:
            _record_rh_identity_auth("skipped", "health_probe", start_time)
            return NO_AUTH_TUPLE
    if request_path == METRICS_SKIP_PATH:
        if configuration.authentication_configuration.skip_for_metrics:
            _record_rh_identity_auth("skipped", "metrics", start_time)
            return NO_AUTH_TUPLE
    return None


class RHIdentityData:
    """Extracts and validates Red Hat Identity header data.

    Supports two identity types:
    - User: Console users with user_id, username, is_org_admin
    - System: Certificate-authenticated RHEL systems with cn as identifier
    """

    def __init__(
        self,
        identity_data: dict,
        required_entitlements: Optional[list[str]] = None,
    ) -> None:
        """Initialize RH Identity data extractor.

        Args:
            identity_data: Decoded JSON from x-rh-identity header
            required_entitlements: Service entitlements to validate (optional)

        Raises:
            HTTPException: If validation fails (400 for format errors, 403 for entitlements)
        """
        self.identity_data = identity_data
        self.required_entitlements = required_entitlements or []
        self._validate_structure()

    def _validate_structure(self) -> None:
        """Validate the identity data structure.

        Raises:
            HTTPException: 400 if required fields are missing or malformed
        """
        if (
            "identity" not in self.identity_data
            or self.identity_data["identity"] is None
        ):
            logger.warning("Identity validation failed: missing 'identity' field")
            raise HTTPException(status_code=400, detail="Invalid identity data")

        identity = self.identity_data["identity"]
        if not isinstance(identity, dict):
            logger.warning(
                "Identity validation failed: 'identity' is %s, expected dict",
                type(identity).__name__,
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        if "type" not in identity:
            logger.warning("Identity validation failed: missing 'type' field")
            raise HTTPException(status_code=400, detail="Invalid identity data")

        identity_type = identity["type"]
        if identity_type == "User":
            self._validate_user_fields(identity)
        elif identity_type == "System":
            self._validate_system_fields(identity)
        else:
            logger.warning("Identity validation failed: unsupported identity type")
            raise HTTPException(status_code=400, detail="Invalid identity data")

        # Validate org_id if present and non-empty
        org_id = identity.get("org_id")
        if org_id is not None and org_id != "":
            self._validate_string_field("org_id", org_id)

    def _validate_user_fields(self, identity: dict) -> None:
        """Validate required fields for User identity type.

        Args:
            identity: The identity dict containing user data

        Raises:
            HTTPException: 400 if required User fields are missing or malformed
        """
        if "user" not in identity:
            logger.warning(
                "Identity validation failed: missing 'user' field for User type"
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        user = identity["user"]
        if "user_id" not in user:
            logger.warning("Identity validation failed: missing 'user_id' in user data")
            raise HTTPException(status_code=400, detail="Invalid identity data")
        if "username" not in user:
            logger.warning(
                "Identity validation failed: missing 'username' in user data"
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        self._validate_string_field("user_id", user["user_id"])
        self._validate_string_field("username", user["username"])

    def _validate_system_fields(self, identity: dict) -> None:
        """Validate required fields for System identity type.

        Args:
            identity: The identity dict containing system data

        Raises:
            HTTPException: 400 if required System fields are missing or malformed
        """
        if "system" not in identity:
            logger.warning(
                "Identity validation failed: missing 'system' field for System type"
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        system = identity["system"]
        if "cn" not in system:
            logger.warning("Identity validation failed: missing 'cn' in system data")
            raise HTTPException(status_code=400, detail="Invalid identity data")
        if "account_number" not in identity:
            logger.warning(
                "Identity validation failed: "
                "missing 'account_number' for System type"
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        self._validate_string_field("cn", system["cn"])
        self._validate_string_field("account_number", identity["account_number"])

    def _validate_string_field(
        self, field_name: str, value: Any, max_length: int = 256
    ) -> None:
        """Validate that a field value is a well-formed string.

        Args:
            field_name: Name of the field being validated (for error messages)
            value: The value to validate
            max_length: Maximum allowed string length

        Raises:
            HTTPException: 400 if validation fails
        """
        if not isinstance(value, str):
            logger.warning(
                "Identity validation failed: %s must be a string, got %s",
                field_name,
                type(value).__name__,
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        if not value.strip():
            logger.warning(
                "Identity validation failed: %s must not be empty",
                field_name,
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        if len(value) > max_length:
            logger.warning(
                "Identity validation failed: %s exceeds maximum length of %d",
                field_name,
                max_length,
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            logger.warning(
                "Identity validation failed: %s contains control characters",
                field_name,
            )
            raise HTTPException(status_code=400, detail="Invalid identity data")

    def _get_identity_type(self) -> str:
        """Get the identity type (User or System).

        Returns:
            Identity type string
        """
        return self.identity_data["identity"]["type"]

    def get_user_id(self) -> str:
        """Extract user ID based on identity type.

        Returns:
            User ID (user.user_id for User type, system.cn for System type)
        """
        identity = self.identity_data["identity"]

        if self._get_identity_type() == "User":
            return identity["user"]["user_id"]
        return identity["system"]["cn"]

    def get_username(self) -> str:
        """Extract username based on identity type.

        Returns:
            Username (user.username for User type, account_number for System type)
        """
        identity = self.identity_data["identity"]

        if self._get_identity_type() == "User":
            return identity["user"]["username"]
        return identity["account_number"]

    def get_org_id(self) -> str:
        """Extract organization ID from identity data.

        Returns:
            Organization ID string, or empty string if not present
        """
        return self.identity_data["identity"].get("org_id", "")

    def get_system_id(self) -> str:
        """Extract system ID from identity data.

        Returns:
            System ID string for System identities, or empty string for User identities
        """
        if self._get_identity_type() == "System":
            return self.identity_data["identity"]["system"]["cn"]
        return ""

    def has_entitlement(self, service: str) -> bool:
        """Check if user has a specific service entitlement.

        Args:
            service: Service name to check (e.g., "rhel", "ansible", "openshift")

        Returns:
            True if user has the entitlement and is_entitled is True
        """
        entitlements = self.identity_data.get("entitlements", {})
        service_entitlement = entitlements.get(service, {})
        return service_entitlement.get("is_entitled", False)

    def has_entitlements(self, services: list[str]) -> bool:
        """Check if user has ALL specified service entitlements.

        Args:
            services: List of service names to check

        Returns:
            True if user has ALL entitlements in the list
        """
        return all(self.has_entitlement(service) for service in services)

    def validate_entitlements(self) -> None:
        """Validate required entitlements based on configuration.

        Raises:
            HTTPException: 403 if required entitlements are missing
        """
        if not self.required_entitlements:
            return  # No validation required

        missing = [s for s in self.required_entitlements if not self.has_entitlement(s)]
        if missing:
            logger.warning(
                "Entitlement validation failed: missing required entitlements: %s",
                ", ".join(missing),
            )
            raise HTTPException(
                status_code=403,
                detail="Insufficient entitlements",
            )


class RHIdentityAuthDependency(AuthInterface):  # pylint: disable=too-few-public-methods
    """Red Hat Identity header authentication dependency for FastAPI.

    Authenticates requests using the x-rh-identity header with base64-encoded JSON.
    Supports both User and System identity types with optional entitlement validation.
    """

    def __init__(
        self,
        required_entitlements: Optional[list[str]] = None,
        virtual_path: str = DEFAULT_VIRTUAL_PATH,
        max_header_size: int = DEFAULT_RH_IDENTITY_MAX_HEADER_SIZE,
    ) -> None:
        """Initialize RH Identity authentication dependency.

        Args:
            required_entitlements: Services to require (ALL must be present)
            virtual_path: Virtual path for authorization checks
            max_header_size: Maximum allowed size in bytes for the base64-encoded
                x-rh-identity header. Headers exceeding this size are rejected
                before decoding.
        """
        self.required_entitlements = required_entitlements
        self.virtual_path = virtual_path
        self.max_header_size = max_header_size
        self.skip_userid_check = False

    async def __call__(self, request: Request) -> AuthTuple:
        """Validate FastAPI request for RH Identity authentication.

        Args:
            request: The FastAPI request object

        Returns:
            AuthTuple: (user_id, username, skip_userid_check, token)

        Raises:
            HTTPException:
                - 401: Missing x-rh-identity header
                - 400: Invalid base64, invalid JSON, or missing required fields
                - 403: Missing required entitlements
        """
        start_time = time.monotonic()

        # Extract header
        identity_header = request.headers.get("x-rh-identity")
        if not identity_header:
            auth_skip = _get_auth_skip_tuple(request, start_time)
            if auth_skip is not None:
                return auth_skip
            logger.warning("Missing x-rh-identity header")
            _record_rh_identity_auth("failure", "missing_header", start_time)
            raise HTTPException(status_code=401, detail="Missing x-rh-identity header")

        # Enforce header size limit before decoding
        if len(identity_header) > self.max_header_size:
            logger.warning(
                "x-rh-identity header size %d exceeds maximum allowed size %d",
                len(identity_header),
                self.max_header_size,
            )
            _record_rh_identity_auth("failure", "header_too_large", start_time)
            raise HTTPException(
                status_code=400,
                detail="x-rh-identity header exceeds maximum allowed size",
            )

        # Decode base64
        try:
            decoded_bytes = base64.b64decode(identity_header, validate=True)
            decoded_str = decoded_bytes.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("Invalid base64 in x-rh-identity header: %s", exc)
            _record_rh_identity_auth("failure", "invalid_base64", start_time)
            raise HTTPException(
                status_code=400,
                detail="Invalid base64 encoding in x-rh-identity header",
            ) from exc

        # Parse JSON
        try:
            identity_data = json.loads(decoded_str)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in x-rh-identity header: %s", exc)
            _record_rh_identity_auth("failure", "invalid_json", start_time)
            raise HTTPException(
                status_code=400, detail="Invalid JSON in x-rh-identity header"
            ) from exc

        # Guard against non-dict JSON payloads (null, list, number, etc.)
        if not isinstance(identity_data, dict):
            logger.warning(
                "x-rh-identity decoded to non-dict type: %s",
                type(identity_data).__name__,
            )
            _record_rh_identity_auth("failure", "invalid_identity", start_time)
            raise HTTPException(
                status_code=400,
                detail="Invalid identity data in x-rh-identity header",
            )

        # Extract and validate identity
        try:
            rh_identity = RHIdentityData(
                identity_data,
                required_entitlements=self.required_entitlements,
            )

            # Validate entitlements if configured
            rh_identity.validate_entitlements()
        except HTTPException as exc:
            reason = (
                "entitlement_missing" if exc.status_code == 403 else "invalid_identity"
            )
            _record_rh_identity_auth("failure", reason, start_time)
            raise

        # Store identity data in request.state for downstream access
        request.state.rh_identity_data = rh_identity

        # Extract user data
        user_id = rh_identity.get_user_id()
        username = rh_identity.get_username()

        logger.info(
            "RH Identity authenticated: request_id=%s, path=%s, org_id=%s, system_id=%s",
            _get_request_id(request),
            request.url.path,
            rh_identity.get_org_id(),
            rh_identity.get_system_id(),
        )
        _record_rh_identity_auth("success", "authenticated", start_time)

        return user_id, username, self.skip_userid_check, NO_USER_TOKEN
