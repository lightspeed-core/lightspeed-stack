"""PoC configuration loader for prompt guardrails (LCORE-2657 spike).

The PoC is wired into the query endpoint only when the
``LCS_GUARDRAILS_POC_CONFIG`` environment variable points at a YAML file
matching :class:`guardrails.models.GuardrailsPocConfig`. Without the
variable the guardrails layer is fully inert, keeping the PoC out of
every existing code path and test.
"""

import os
from functools import lru_cache
from typing import Final, Optional

import yaml

from guardrails.models import GuardrailsPocConfig
from log import get_logger

logger = get_logger(__name__)

POC_CONFIG_ENV_VAR: Final[str] = "LCS_GUARDRAILS_POC_CONFIG"


@lru_cache(maxsize=1)
def load_poc_config() -> Optional[GuardrailsPocConfig]:
    """Load the PoC guardrails configuration, if enabled.

    Returns:
    -------
        Optional[GuardrailsPocConfig]: The parsed configuration when the
        environment variable is set; None when the PoC is disabled.
    """
    config_path = os.environ.get(POC_CONFIG_ENV_VAR)
    if not config_path:
        return None
    with open(config_path, encoding="utf-8") as config_file:
        raw_config = yaml.safe_load(config_file)
    config = GuardrailsPocConfig.model_validate(raw_config)
    logger.warning(
        "Prompt guardrails PoC ACTIVE: %d rules, detector=%s model=%s",
        len(config.rules),
        config.detector.url,
        config.detector.model,
    )
    return config
