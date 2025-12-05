"""Red Hat Identity header authentication for FastAPI endpoints.

This module provides authentication via the x-rh-identity header, supporting both
User and System identity types with optional entitlement validation.
"""

import base64
import json
import logging
from typing import Optional

from fastapi import HTTPException, Request

from authentication.interface import AuthInterface, AuthTuple
from constants import DEFAULT_VIRTUAL_PATH, NO_USER_TOKEN

logger = logging.getLogger(__name__)


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
            HTTPException: 400 if required fields are missing
        """
        if (
            "identity" not in self.identity_data
            or self.identity_data["identity"] is None
        ):
            raise HTTPException(status_code=400, detail="Missing 'identity' field")

        identity = self.identity_data["identity"]
        if "type" not in identity:
            raise HTTPException(status_code=400, detail="Missing identity 'type' field")

        identity_type = identity["type"]
        if identity_type == "User":
            if "user" not in identity:
                raise HTTPException(
                    status_code=400, detail="Missing 'user' field for User type"
                )
            user = identity["user"]
            if "user_id" not in user:
                raise HTTPException(
                    status_code=400, detail="Missing 'user_id' in user data"
                )
            if "username" not in user:
                raise HTTPException(
                    status_code=400, detail="Missing 'username' in user data"
                )
        elif identity_type == "System":
            if "system" not in identity:
                raise HTTPException(
                    status_code=400, detail="Missing 'system' field for System type"
                )
            system = identity["system"]
            if "cn" not in system:
                raise HTTPException(
                    status_code=400, detail="Missing 'cn' in system data"
                )
            if "account_number" not in identity:
                raise HTTPException(
                    status_code=400, detail="Missing 'account_number' for System type"
                )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported identity type: {identity_type}"
            )

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
            entitlement_word = "entitlement" if len(missing) == 1 else "entitlements"
            raise HTTPException(
                status_code=403,
                detail=f"Missing required {entitlement_word}: {', '.join(missing)}",
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
    ) -> None:
        """Initialize RH Identity authentication dependency.

        Args:
            required_entitlements: Services to require (ALL must be present)
            virtual_path: Virtual path for authorization checks
        """
        self.required_entitlements = required_entitlements
        self.virtual_path = virtual_path
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
        # Extract header
        identity_header = request.headers.get("x-rh-identity")
        if not identity_header:
            logger.warning("Missing x-rh-identity header")
            raise HTTPException(status_code=401, detail="Missing x-rh-identity header")

        # Decode base64
        try:
            decoded_bytes = base64.b64decode(identity_header, validate=True)
            decoded_str = decoded_bytes.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            logger.warning("Invalid base64 in x-rh-identity header: %s", exc)
            raise HTTPException(
                status_code=400,
                detail="Invalid base64 encoding in x-rh-identity header",
            ) from exc

        # Parse JSON
        try:
            identity_data = json.loads(decoded_str)
        except json.JSONDecodeError as exc:
            logger.warning("Invalid JSON in x-rh-identity header: %s", exc)
            raise HTTPException(
                status_code=400, detail="Invalid JSON in x-rh-identity header"
            ) from exc

        # Extract and validate identity
        rh_identity = RHIdentityData(
            identity_data,
            required_entitlements=self.required_entitlements,
        )

        # Validate entitlements if configured
        rh_identity.validate_entitlements()

        # Extract user data
        user_id = rh_identity.get_user_id()
        username = rh_identity.get_username()

        logger.debug(
            "RH Identity authenticated: user_id=%s, username=%s", user_id, username
        )

        return user_id, username, self.skip_userid_check, NO_USER_TOKEN
