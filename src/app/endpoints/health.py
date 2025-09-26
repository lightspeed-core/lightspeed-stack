"""Handlers for health REST API endpoints.

These endpoints are used to check if service is live and prepared to accept
requests. Note that these endpoints can be accessed using GET or HEAD HTTP
methods. For HEAD HTTP method, just the HTTP response code is used.
"""

import logging
import re
from typing import Any, Dict, List

from llama_stack.providers.datatypes import HealthStatus

from fastapi import APIRouter, status, Response
from client import AsyncLlamaStackClientHolder
from models.responses import (
    LivenessResponse,
    ReadinessResponse,
    ProviderHealthStatus,
)
from configuration import configuration
from app.state import app_state

logger = logging.getLogger("app.endpoints.handlers")
router = APIRouter(tags=["health"])

def find_unresolved_template_placeholders(obj: Any, path: str = "") -> List[tuple[str, str]]:
    r"""
    Recursively search for unresolved template placeholders in configuration.
    
    Detects patterns like:
    - ${VARIABLE_NAME} (basic template format) 
    - ${\{VARIABLE_NAME}} (malformed template)
    - ${env.VARIABLE_NAME} (llama-stack format)
    
    Returns list of (path, value) tuples for any unresolved placeholders.
    """
    unresolved = []
    
    # Patterns that indicate unresolved template placeholders
    template_patterns = [
        r'\$\{\\?\{[^}]+\}\\?\}',      # Malformed: ${\{VARIABLE}} (check first)
        r'\$\{env\.[^}]+\}',           # llama-stack env: ${env.VARIABLE}  
        r'\$\{[^}]+\}',                # Basic: ${VARIABLE} (check last)
    ]
    
    def check_string_for_patterns(value: str, current_path: str):
        """Check if a string contains unresolved template patterns."""
        for pattern in template_patterns:
            matches = re.findall(pattern, value)
            if matches:
                unresolved.append((current_path, matches[0]))
                break  # Stop after first match to avoid duplicates
    
    def walk_object(obj: Any, current_path: str = ""):
        """Recursively walk the configuration object."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{current_path}.{key}" if current_path else key
                walk_object(value, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                new_path = f"{current_path}[{i}]"
                walk_object(item, new_path)
        elif isinstance(obj, str):
            check_string_for_patterns(obj, current_path)
    
    walk_object(obj, path)
    return unresolved


def check_comprehensive_readiness() -> tuple[bool, str]:
    """
    Comprehensive readiness check that validates configuration and initialization.
    
    Checks in order of importance:
    1. Configuration loading and validation  
    2. Application initialization state
    3. Template placeholder resolution
    
    Returns:
        tuple[bool, str]: (is_ready, detailed_reason)
    """
    try:
        # Check 1: Configuration loading
        if not configuration.is_loaded():
            # Check if we have detailed error from app_state
            status = app_state.initialization_status
            for error in status['errors']:
                if 'configuration' in error.lower():
                    return False, f"Configuration loading failed: {error.split(':', 1)[1].strip()}"
            return False, "Configuration not loaded"
        
        # Check 2: Template placeholders (critical - causes pydantic errors)
        unresolved_placeholders = find_unresolved_template_placeholders(configuration.configuration)
        if unresolved_placeholders:
            # Prioritize showing the most problematic placeholders
            example_path, example_value = unresolved_placeholders[0]
            count = len(unresolved_placeholders)
            if count == 1:
                return False, f"Unresolved template placeholder in {example_path}: {example_value}"
            else:
                return False, f"Found {count} unresolved template placeholders (e.g., {example_path}: {example_value})"
        
        # Check 3: Application initialization state
        if not app_state.is_fully_initialized:
            status = app_state.initialization_status
            failed_checks = [k for k, v in status['checks'].items() if not v]
            
            # Return specific error if available
            for error in status['errors']:
                # Return first non-configuration error (those are already handled above)
                if not any(check in error.lower() for check in ['configuration']):
                    error_detail = error.split(':', 1)[1].strip() if ':' in error else error
                    return False, f"Initialization failed: {error_detail}"
            
            # Fallback to listing failed checks
            if failed_checks:
                failed_names = [check.replace('_', ' ').title() for check in failed_checks]
                return False, f"Incomplete initialization: {', '.join(failed_names)}"
            
            return False, "Application initialization not complete"
        
        return True, "Service ready"
        
    except Exception as e:
        return False, f"Readiness check error: {str(e)}"


async def get_providers_health_statuses() -> list[ProviderHealthStatus]:
    """
    Retrieve the health status of all configured providers.

    Returns:
        list[ProviderHealthStatus]: A list containing the health
        status of each provider. If provider health cannot be
        determined, returns a single entry indicating an error.
    """
    try:
        client = AsyncLlamaStackClientHolder().get_client()

        providers = await client.providers.list()
        logger.debug("Found %d providers", len(providers))

        health_results = [
            ProviderHealthStatus(
                provider_id=provider.provider_id,
                status=str(provider.health.get("status", "unknown")),
                message=str(provider.health.get("message", "")),
            )
            for provider in providers
        ]
        return health_results

    except Exception as e:  # pylint: disable=broad-exception-caught
        # eg. no providers defined
        logger.error("Failed to check providers health: %s", e)
        return [
            ProviderHealthStatus(
                provider_id="unknown",
                status=HealthStatus.ERROR.value,
                message=f"Failed to initialize health check: {str(e)}",
            )
        ]


get_readiness_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Service is ready",
        "model": ReadinessResponse,
    },
    503: {
        "description": "Service is not ready",
        "model": ReadinessResponse,
    },
}


@router.get("/readiness", responses=get_readiness_responses)
async def readiness_probe_get_method(
    response: Response,
) -> ReadinessResponse:
    """
    Enhanced readiness probe that validates complete application readiness.
    
    This probe performs comprehensive checks including:
    1. Configuration loading and validation (detects unresolved template placeholders)
    2. Application initialization state (startup sequence completion)
    3. LLM provider health status (existing functionality)
    
    The probe helps detect issues like:
    - Configuration loading failures (pydantic validation errors)
    - Unresolved environment variables (${VARIABLE} patterns)
    - Incomplete application startup (llama client, MCP servers, etc.)
    - Provider connectivity problems
    
    Returns 200 when fully ready, 503 when any issues are detected.
    Each failure mode provides specific diagnostic information in the response.
    """
    logger.info("Response to /v1/readiness endpoint")

    # Comprehensive configuration and initialization check
    config_and_init_ready, reason = check_comprehensive_readiness()
    if not config_and_init_ready:
        # Configuration/initialization issues are critical - return immediately
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(ready=False, reason=reason, providers=[])

    # Provider health check (only if configuration/initialization is ready)
    try:
        provider_statuses = await get_providers_health_statuses()
        unhealthy_providers = [
            p for p in provider_statuses if p.status == HealthStatus.ERROR.value
        ]

        if unhealthy_providers:
            unhealthy_provider_names = [p.provider_id for p in unhealthy_providers]
            reason = f"Unhealthy providers: {', '.join(unhealthy_provider_names)}"
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return ReadinessResponse(ready=False, reason=reason, providers=unhealthy_providers)

    except Exception as e:
        reason = f"Provider health check failed: {str(e)}"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(ready=False, reason=reason, providers=[])

    # All checks passed
    return ReadinessResponse(ready=True, reason="Application fully initialized and ready", providers=[])


get_liveness_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Service is alive",
        "model": LivenessResponse,
    },
    # HTTP_503_SERVICE_UNAVAILABLE will never be returned when unreachable
}


@router.get("/liveness", responses=get_liveness_responses)
async def liveness_probe_get_method() -> LivenessResponse:
    """
    Return the liveness status of the service.

    Returns:
        LivenessResponse: Indicates that the service is alive.
    """

    logger.info("Response to /v1/liveness endpoint")

    return LivenessResponse(alive=True)
