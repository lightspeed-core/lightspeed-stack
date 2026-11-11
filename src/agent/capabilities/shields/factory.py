"""Factory for building shield capabilities from shield settings."""

from typing import Optional

from agent.types.settings import ShieldSettings
from configuration import configuration
from log import get_logger
from models.config import (
    GraniteGuardianConfig,
    QuestionValidityConfig,
    RedactionConfig,
)
from pydantic_ai_lightspeed.capabilities import QuestionValidity
from pydantic_ai_lightspeed.capabilities.base import AbstractSafetyCapability
from pydantic_ai_lightspeed.capabilities.granite_guardian import GraniteGuardian
from pydantic_ai_lightspeed.capabilities.redaction import PiiRedactionCapability

logger = get_logger(__name__)


class ShieldFactory:
    """Factory for building shield capabilities."""

    @staticmethod
    def build_capability(
        settings: ShieldSettings,
    ) -> Optional[AbstractSafetyCapability]:
        """Build a shield capability from shield settings.

        The shield named by ``settings.id`` is loaded from the process-wide
        configuration. Disabled settings and unknown names produce no
        capability.

        Parameters:
            settings: Shield settings.

        Returns:
            A shield capability, or ``None`` when the shield is disabled or
            no matching named shield is configured.

        Raises:
            ValueError: If the matching shield uses an unsupported config type.

        """
        if not settings.enabled:
            return None

        shield = next(
            (
                configured
                for configured in configuration.shields
                if configured.name == settings.id
            ),
            None,
        )

        if shield is None:
            logger.warning(
                "Shield '%s' is not configured; skipping shield capability",
                settings.id,
            )
            return None

        match shield.config:
            case QuestionValidityConfig():
                return QuestionValidity(config=shield.config)
            case RedactionConfig():
                return PiiRedactionCapability(config=shield.config)
            case GraniteGuardianConfig():
                return GraniteGuardian(config=shield.config)
            case _:
                raise ValueError(
                    f"Unsupported shield config type for shield '{shield.name}': "
                    f"{type(shield.config).__name__}"
                )

    @staticmethod
    def build_capabilities(
        settings: list[ShieldSettings],
    ) -> list[AbstractSafetyCapability]:
        """Build shield capabilities from all shield settings.

        Parameters:
            settings: Shield settings to turn into capabilities.

        Returns:
            One capability per enabled setting that matches a configured
            shield name, in the same order.

        """
        if not settings:
            return []

        return [
            capability
            for setting in settings
            if (capability := ShieldFactory.build_capability(setting)) is not None
        ]
