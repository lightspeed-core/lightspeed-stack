"""Llama Stack client retrieval class."""

import logging
import ssl
from typing import Optional

import httpx
from llama_stack import (
    AsyncLlamaStackAsLibraryClient,  # type: ignore
)
from llama_stack_client import AsyncLlamaStackClient  # type: ignore
from models.config import LlamaStackConfiguration, TLSSecurityProfile
from utils.types import Singleton
from utils import tls


logger = logging.getLogger(__name__)


class AsyncLlamaStackClientHolder(metaclass=Singleton):
    """Container for an initialised AsyncLlamaStackClient."""

    _lsc: Optional[AsyncLlamaStackClient] = None

    def _construct_httpx_client(
        self, tls_security_profile: Optional[TLSSecurityProfile]
    ) -> Optional[httpx.AsyncClient]:
        """Construct HTTPX client with TLS security profile configuration.

        Args:
            tls_security_profile: TLS security profile configuration.

        Returns:
            Configured httpx.AsyncClient if TLS profile is set, None otherwise.
        """
        # if security profile is not set, return None to use default httpx client
        if tls_security_profile is None or tls_security_profile.profile_type is None:
            logger.info("No TLS security profile configured, using default settings")
            return None

        logger.info("TLS security profile: %s", tls_security_profile.profile_type)

        # get the TLS profile type
        profile_type = tls.TLSProfiles(tls_security_profile.profile_type)

        # retrieve ciphers - custom list or profile-based
        ciphers = tls.ciphers_as_string(tls_security_profile.ciphers, profile_type)
        logger.info("TLS ciphers: %s", ciphers)

        # retrieve minimum TLS version
        min_tls_ver = tls.min_tls_version(
            tls_security_profile.min_tls_version, profile_type
        )
        logger.info("Minimum TLS version: %s", min_tls_ver)

        ssl_version = tls.ssl_tls_version(min_tls_ver)
        logger.info("SSL version: %s", ssl_version)

        # check if TLS verification should be skipped (for testing only)
        if tls_security_profile.skip_tls_verification:
            logger.warning(
                "TLS verification is disabled. This is insecure and should "
                "only be used for testing purposes."
            )
            return httpx.AsyncClient(verify=False)

        # create SSL context with the configured settings
        context = ssl.create_default_context()

        # load CA certificate if specified
        if tls_security_profile.ca_cert_path is not None:
            logger.info("Loading CA certificate from: %s", tls_security_profile.ca_cert_path)
            context.load_verify_locations(cafile=str(tls_security_profile.ca_cert_path))

        if ssl_version is not None:
            context.minimum_version = ssl_version

        if ciphers is not None:
            # Note: TLS 1.3 ciphers cannot be set via set_ciphers() - they are
            # automatically negotiated when TLS 1.3 is used. The set_ciphers()
            # method only affects TLS 1.2 and below cipher selection.
            try:
                context.set_ciphers(ciphers)
            except ssl.SSLError as e:
                logger.warning(
                    "Could not set ciphers '%s': %s. "
                    "TLS 1.3 ciphers are automatically negotiated.",
                    ciphers,
                    e,
                )

        logger.info("Creating httpx.AsyncClient with TLS security profile")
        return httpx.AsyncClient(verify=context)

    async def load(self, llama_stack_config: LlamaStackConfiguration) -> None:
        """
        Load and initialize the holder's AsyncLlamaStackClient according to the provided config.

        If `llama_stack_config.use_as_library_client` is set to True, a
        library-mode client is created using
        `llama_stack_config.library_client_config_path` and initialized before
        being stored.

        Otherwise, a service-mode client is created using
        `llama_stack_config.url` and optional `llama_stack_config.api_key`.
        The created client is stored on the instance for later retrieval via
        `get_client()`.

        Parameters:
            llama_stack_config (LlamaStackConfiguration): Configuration that
            selects client mode and provides either a library client config
            path or service connection details (URL and optional API key).

        Raises:
            ValueError: If `use_as_library_client` is True but
            `library_client_config_path` is not set.
        """
        if llama_stack_config.use_as_library_client is True:
            if llama_stack_config.library_client_config_path is not None:
                logger.info("Using Llama stack as library client")
                client = AsyncLlamaStackAsLibraryClient(
                    llama_stack_config.library_client_config_path
                )
                await client.initialize()
                self._lsc = client
            else:
                msg = "Configuration problem: library_client_config_path option is not set"
                logger.error(msg)
                # tisnik: use custom exception there - with cause etc.
                raise ValueError(msg)
        else:
            logger.info("Using Llama stack running as a service")

            # construct httpx client with TLS security profile if configured
            http_client = self._construct_httpx_client(
                llama_stack_config.tls_security_profile
            )

            self._lsc = AsyncLlamaStackClient(
                base_url=llama_stack_config.url,
                api_key=(
                    llama_stack_config.api_key.get_secret_value()
                    if llama_stack_config.api_key is not None
                    else None
                ),
                http_client=http_client,
            )

    def get_client(self) -> AsyncLlamaStackClient:
        """
        Get the initialized client held by this holder.

        Returns:
            AsyncLlamaStackClient: The initialized client instance.

        Raises:
            RuntimeError: If the client has not been initialized; call `load(...)` first.
        """
        if not self._lsc:
            raise RuntimeError(
                "AsyncLlamaStackClient has not been initialised. Ensure 'load(..)' has been called."
            )
        return self._lsc
