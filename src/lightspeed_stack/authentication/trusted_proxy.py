"""Trusted-proxy authentication module for requests forwarded by a K8s proxy."""

from typing import cast

import kubernetes.client
from fastapi import HTTPException, Request

from authentication.interface import NO_AUTH_TUPLE, AuthInterface, AuthTuple
from authentication.k8s import get_user_info
from authentication.utils import extract_user_token
from configuration import configuration
from constants import DEFAULT_VIRTUAL_PATH, NO_USER_TOKEN
from log import get_logger
from models.api.responses.error import ForbiddenResponse, UnauthorizedResponse
from models.config import TrustedProxyConfiguration

logger = get_logger(__name__)


class TrustedProxyAuthDependency(
    AuthInterface
):  # pylint: disable=too-few-public-methods
    """FastAPI dependency for trusted-proxy authentication.

    Validates that the caller is an expected Kubernetes ServiceAccount
    via TokenReview, then extracts the end user's identity from a
    configurable HTTP header set by the proxy.
    """

    def __init__(
        self,
        config: TrustedProxyConfiguration,
        virtual_path: str = DEFAULT_VIRTUAL_PATH,
    ) -> None:
        """Initialize the trusted-proxy authentication dependency.

        Parameters:
        ----------
            config: Trusted-proxy configuration with user header
                    and optional SA allowlist.
            virtual_path: The request path used for authorization checks;
                          defaults to DEFAULT_VIRTUAL_PATH.
        """
        self.config = config
        self.virtual_path = virtual_path
        self.skip_userid_check = True

    async def __call__(self, request: Request) -> AuthTuple:
        """Validate the proxy's SA token and extract forwarded user identity.

        Parameters:
        ----------
            request: The FastAPI request object.

        Returns:
        -------
            AuthTuple with the forwarded user identity.

        Raises:
        ------
            HTTPException: If authentication fails.
        """
        if not request.headers.get("Authorization"):
            if configuration.authentication_configuration.skip_for_health_probes:
                if request.url.path in ("/readiness", "/liveness"):
                    return NO_AUTH_TUPLE
            if configuration.authentication_configuration.skip_for_metrics:
                if request.url.path == "/metrics":
                    return NO_AUTH_TUPLE
            response = UnauthorizedResponse(cause="Missing Authorization header")
            raise HTTPException(**response.model_dump())

        token = extract_user_token(request.headers)
        user_info = get_user_info(token)

        if user_info is None:
            response = UnauthorizedResponse(
                cause="Invalid or expired proxy service account token"
            )
            raise HTTPException(**response.model_dump())

        user = cast(kubernetes.client.V1UserInfo, user_info.user)
        if not user or not hasattr(user, "username"):
            response = UnauthorizedResponse(
                cause="Invalid service account token: missing user information"
            )
            raise HTTPException(**response.model_dump())

        sa_username = cast(str, user.username)
        if not sa_username:
            response = UnauthorizedResponse(
                cause="Invalid service account token: missing username"
            )
            raise HTTPException(**response.model_dump())

        if self.config.allowed_service_accounts:
            allowed = {
                f"system:serviceaccount:{sa.namespace}:{sa.name}"
                for sa in self.config.allowed_service_accounts
            }
            if sa_username not in allowed:
                logger.warning(
                    "Service account '%s' is not in the trusted-proxy allowlist",
                    sa_username,
                )
                response = ForbiddenResponse.endpoint(user_id=sa_username)
                raise HTTPException(**response.model_dump())

        forwarded_user = (request.headers.get(self.config.user_header) or "").strip()
        if not forwarded_user:
            response = UnauthorizedResponse(
                cause=f"Missing required header '{self.config.user_header}'"
            )
            raise HTTPException(**response.model_dump())

        logger.debug(
            "Trusted-proxy auth: proxy='%s', forwarded_user_present=%s",
            sa_username,
            True,
        )

        return (
            forwarded_user,
            forwarded_user,
            self.skip_userid_check,
            NO_USER_TOKEN,
        )
