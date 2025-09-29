"""Unit tests for the /health REST API endpoint."""

from unittest.mock import Mock, patch

import pytest
from llama_stack.providers.datatypes import HealthStatus
from app.endpoints.health import (
    readiness_probe_get_method,
    liveness_probe_get_method,
    get_providers_health_statuses,
    find_unresolved_template_placeholders,
    check_comprehensive_readiness,
)
from models.responses import ProviderHealthStatus, ReadinessResponse


@pytest.mark.asyncio
async def test_readiness_probe_fails_due_to_unhealthy_providers(mocker):
    """Test the readiness endpoint handler fails when providers are unhealthy."""
    # Mock comprehensive readiness to pass config/init checks but fail providers
    mock_comprehensive_readiness = mocker.patch(
        "app.endpoints.health.check_comprehensive_readiness"
    )
    mock_comprehensive_readiness.return_value = (True, "")
    
    # Mock get_providers_health_statuses to return an unhealthy provider
    mock_get_providers_health_statuses = mocker.patch(
        "app.endpoints.health.get_providers_health_statuses"
    )
    mock_get_providers_health_statuses.return_value = [
        ProviderHealthStatus(
            provider_id="test_provider",
            status=HealthStatus.ERROR.value,
            message="Provider is down",
        )
    ]

    # Mock the Response object (no auth needed)
    mock_response = Mock()

    response = await readiness_probe_get_method(response=mock_response)

    assert response.ready is False
    assert "test_provider" in response.reason
    assert "Unhealthy providers:" in response.reason
    assert mock_response.status_code == 503


@pytest.mark.asyncio
async def test_readiness_probe_success_when_all_providers_healthy(mocker):
    """Test the readiness endpoint handler succeeds when all providers are healthy."""
    # Mock comprehensive readiness to pass config/init checks
    mock_comprehensive_readiness = mocker.patch(
        "app.endpoints.health.check_comprehensive_readiness"
    )
    mock_comprehensive_readiness.return_value = (True, "")
    
    # Mock get_providers_health_statuses to return healthy providers
    mock_get_providers_health_statuses = mocker.patch(
        "app.endpoints.health.get_providers_health_statuses"
    )
    mock_get_providers_health_statuses.return_value = [
        ProviderHealthStatus(
            provider_id="provider1",
            status=HealthStatus.OK.value,
            message="Provider is healthy",
        ),
        ProviderHealthStatus(
            provider_id="provider2",
            status=HealthStatus.NOT_IMPLEMENTED.value,
            message="Provider does not implement health check",
        ),
    ]

    # Mock the Response object (no auth needed)
    mock_response = Mock()

    response = await readiness_probe_get_method(response=mock_response)
    assert response is not None
    assert isinstance(response, ReadinessResponse)
    assert response.ready is True
    assert response.reason == "Application fully initialized and ready"
    # Should return empty list since no providers are unhealthy
    assert len(response.providers) == 0


@pytest.mark.asyncio
async def test_liveness_probe():
    """Test the liveness endpoint handler."""
    response = await liveness_probe_get_method()
    assert response is not None
    assert response.alive is True


class TestProviderHealthStatus:
    """Test cases for the ProviderHealthStatus model."""

    def test_provider_health_status_creation(self):
        """Test creating a ProviderHealthStatus instance."""
        status = ProviderHealthStatus(
            provider_id="test_provider", status="ok", message="All good"
        )
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message == "All good"

    def test_provider_health_status_optional_fields(self):
        """Test creating a ProviderHealthStatus with minimal fields."""
        status = ProviderHealthStatus(provider_id="test_provider", status="ok")
        assert status.provider_id == "test_provider"
        assert status.status == "ok"
        assert status.message is None


class TestGetProvidersHealthStatuses:
    """Test cases for the get_providers_health_statuses function."""

    async def test_get_providers_health_statuses(self, mocker):
        """Test get_providers_health_statuses with healthy providers."""
        # Mock the imports
        mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")

        # Mock the client and its methods
        mock_client = mocker.AsyncMock()
        mock_lsc.return_value = mock_client

        # Mock providers.list() to return providers with health
        mock_provider_1 = mocker.Mock()
        mock_provider_1.provider_id = "provider1"
        mock_provider_1.health = {
            "status": HealthStatus.OK.value,
            "message": "All good",
        }

        mock_provider_2 = mocker.Mock()
        mock_provider_2.provider_id = "provider2"
        mock_provider_2.health = {
            "status": HealthStatus.NOT_IMPLEMENTED.value,
            "message": "Provider does not implement health check",
        }

        mock_provider_3 = mocker.Mock()
        mock_provider_3.provider_id = "unhealthy_provider"
        mock_provider_3.health = {
            "status": HealthStatus.ERROR.value,
            "message": "Connection failed",
        }

        mock_client.providers.list.return_value = [
            mock_provider_1,
            mock_provider_2,
            mock_provider_3,
        ]

        # Mock configuration
        result = await get_providers_health_statuses()

        assert len(result) == 3
        assert result[0].provider_id == "provider1"
        assert result[0].status == HealthStatus.OK.value
        assert result[0].message == "All good"
        assert result[1].provider_id == "provider2"
        assert result[1].status == HealthStatus.NOT_IMPLEMENTED.value
        assert result[1].message == "Provider does not implement health check"
        assert result[2].provider_id == "unhealthy_provider"
        assert result[2].status == HealthStatus.ERROR.value
        assert result[2].message == "Connection failed"

    async def test_get_providers_health_statuses_connection_error(self, mocker):
        """Test get_providers_health_statuses when connection fails."""
        # Mock the imports
        mock_lsc = mocker.patch("client.AsyncLlamaStackClientHolder.get_client")

        # Mock get_llama_stack_client to raise an exception
        mock_lsc.side_effect = Exception("Connection error")

        result = await get_providers_health_statuses()

        assert len(result) == 1
        assert result[0].provider_id == "unknown"
        assert result[0].status == HealthStatus.ERROR.value
        assert (
            result[0].message == "Failed to initialize health check: Connection error"
        )


# ============================================================================
# NEW COMPREHENSIVE READINESS PROBE TESTS
# ============================================================================

class TestFindUnresolvedTemplatePlaceholders:
    """Test cases for the find_unresolved_template_placeholders function."""

    def test_finds_basic_template_placeholders(self):
        """Test detection of basic ${VAR} placeholders."""
        config = {
            "database": {
                "host": "${DB_HOST}",
                "port": 5432,
                "name": "production"
            },
            "api_key": "${API_KEY}"
        }
        
        result = find_unresolved_template_placeholders(config)
        
        assert len(result) == 2
        paths = [item[0] for item in result]
        values = [item[1] for item in result]
        
        assert "database.host" in paths
        assert "api_key" in paths
        assert "${DB_HOST}" in values
        assert "${API_KEY}" in values

    def test_finds_malformed_template_placeholders(self):
        """Test detection of malformed ${\\{VAR}} placeholders."""
        config = {
            "auth": {
                "role_rules": "${{AUTHN_ROLE_RULES}}",
                "access_rules": "${{AUTHZ_ACCESS_RULES}}"
            }
        }
        
        result = find_unresolved_template_placeholders(config)
        
        assert len(result) == 2
        paths = [item[0] for item in result]
        values = [item[1] for item in result]
        
        assert "auth.role_rules" in paths
        assert "auth.access_rules" in paths
        assert "${{AUTHN_ROLE_RULES}}" in values
        assert "${{AUTHZ_ACCESS_RULES}}" in values

    def test_finds_env_template_placeholders(self):
        """Test detection of ${env.VAR} placeholders."""
        config = {
            "llama_stack": {
                "url": "${env.LLAMA_STACK_URL}",
                "timeout": 30
            }
        }
        
        result = find_unresolved_template_placeholders(config)
        
        assert len(result) == 1
        assert result[0][0] == "llama_stack.url"
        assert result[0][1] == "${env.LLAMA_STACK_URL}"

    def test_ignores_resolved_values(self):
        """Test that normal values are not flagged as placeholders."""
        config = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "name": "production"
            },
            "features": {
                "enabled": True,
                "count": 10
            },
            "nested": {
                "array": ["item1", "item2"],
                "object": {"key": "value"}
            }
        }
        
        result = find_unresolved_template_placeholders(config)
        
        assert len(result) == 0

    def test_handles_nested_structures(self):
        """Test placeholder detection in deeply nested structures."""
        config = {
            "level1": {
                "level2": {
                    "level3": {
                        "deep_config": "${DEEP_VAR}",
                        "normal_value": "resolved"
                    },
                    "array": ["${ARRAY_VAR}", "normal_item"]
                }
            }
        }
        
        result = find_unresolved_template_placeholders(config)
        
        assert len(result) == 2
        paths = [item[0] for item in result]
        
        assert "level1.level2.level3.deep_config" in paths
        assert "level1.level2.array[0]" in paths

    def test_handles_arrays_with_placeholders(self):
        """Test placeholder detection in arrays."""
        config = {
            "roles": ["admin", "${USER_ROLE}", "guest"],
            "permissions": ["read", "${WRITE_PERM}"]
        }
        
        result = find_unresolved_template_placeholders(config)
        
        assert len(result) == 2
        paths = [item[0] for item in result]
        
        assert "roles[1]" in paths
        assert "permissions[1]" in paths


class TestCheckComprehensiveReadiness:
    """Test cases for the check_comprehensive_readiness function."""

    @patch('app.endpoints.health.app_state')
    @patch('app.endpoints.health.configuration')
    def test_fails_when_configuration_not_loaded(self, mock_configuration, mock_app_state):
        """Test readiness check fails when configuration is not loaded."""
        mock_configuration.is_loaded.return_value = False
        mock_app_state.is_fully_initialized = False
        mock_app_state.initialization_status = {
            'checks': {'configuration_loaded': False},
            'errors': ["Config load failed"]
        }
        
        ready, reason = check_comprehensive_readiness()
        
        assert ready is False
        assert "Configuration not loaded" in reason

    @patch('app.endpoints.health.app_state')
    @patch('app.endpoints.health.configuration')
    def test_fails_when_initialization_incomplete(self, mock_configuration, mock_app_state):
        """Test readiness check fails when application initialization is incomplete."""
        mock_configuration.is_loaded.return_value = True
        mock_app_state.is_fully_initialized = False
        mock_app_state.initialization_status = {
            'checks': {
                'configuration_loaded': True,
                'configuration_valid': True,
                'llama_client_initialized': False,
                'mcp_servers_registered': False
            },
            'errors': []
        }
        
        ready, reason = check_comprehensive_readiness()
        
        assert ready is False
        assert "Incomplete initialization" in reason
        assert "Llama Client Initialized" in reason
        assert "Mcp Servers Registered" in reason

    @patch('app.endpoints.health.app_state')
    @patch('app.endpoints.health.configuration')
    def test_succeeds_when_fully_ready(self, mock_configuration, mock_app_state):
        """Test readiness check succeeds when everything is ready."""
        mock_configuration.is_loaded.return_value = True
        mock_app_state.is_fully_initialized = True
        
        ready, reason = check_comprehensive_readiness()

        assert ready is True
        assert reason == "Service ready"

    @patch('app.endpoints.health.app_state')
    @patch('app.endpoints.health.configuration')
    @patch('app.endpoints.health.find_unresolved_template_placeholders')
    def test_detects_template_placeholders_in_config(self, mock_find_placeholders, mock_configuration, mock_app_state):
        """Test readiness check detects unresolved template placeholders."""
        mock_configuration.is_loaded.return_value = True
        mock_configuration.configuration.model_dump.return_value = {"test": "config"}
        mock_app_state.is_fully_initialized = False
        mock_app_state.initialization_status = {
            'checks': {'configuration_loaded': False},
            'errors': []
        }
        
        # Mock template placeholders detection
        mock_find_placeholders.return_value = [
            ("auth.role_rules", "${{AUTHN_ROLE_RULES}}"),
            ("auth.access_rules", "${{AUTHZ_ACCESS_RULES}}")
        ]
        
        ready, reason = check_comprehensive_readiness()
        
        assert ready is False
        assert "Found 2 unresolved template placeholders" in reason
        assert "auth.role_rules: ${{AUTHN_ROLE_RULES}}" in reason


class TestEnhancedReadinessProbe:
    """Test cases for enhanced readiness probe functionality."""

    @pytest.mark.asyncio
    async def test_readiness_fails_on_configuration_error(self, mocker):
        """Test readiness probe fails when configuration has errors."""
        mock_comprehensive_readiness = mocker.patch(
            "app.endpoints.health.check_comprehensive_readiness"
        )
        mock_comprehensive_readiness.return_value = (False, "Configuration error: Template placeholders unresolved")
        
        mock_response = Mock()
        
        response = await readiness_probe_get_method(response=mock_response)
        
        assert response.ready is False
        assert "Configuration error" in response.reason
        assert mock_response.status_code == 503

    @pytest.mark.asyncio
    async def test_readiness_fails_on_initialization_incomplete(self, mocker):
        """Test readiness probe fails when initialization is incomplete."""
        mock_comprehensive_readiness = mocker.patch(
            "app.endpoints.health.check_comprehensive_readiness"
        )
        mock_comprehensive_readiness.return_value = (False, "Incomplete initialization: llama_client_initialized, mcp_servers_registered")
        
        mock_response = Mock()
        
        response = await readiness_probe_get_method(response=mock_response)
        
        assert response.ready is False
        assert "Incomplete initialization" in response.reason
        assert mock_response.status_code == 503

    @pytest.mark.asyncio
    async def test_readiness_prioritizes_config_errors_over_provider_errors(self, mocker):
        """Test that configuration errors are prioritized over provider health issues."""
        # Configuration/init check fails
        mock_comprehensive_readiness = mocker.patch(
            "app.endpoints.health.check_comprehensive_readiness"
        )
        mock_comprehensive_readiness.return_value = (False, "Configuration error: Critical failure")
        
        # Provider check would also fail, but should not be reached
        mock_get_providers_health_statuses = mocker.patch(
            "app.endpoints.health.get_providers_health_statuses"
        )
        mock_get_providers_health_statuses.return_value = [
            ProviderHealthStatus(
                provider_id="failing_provider",
                status=HealthStatus.ERROR.value,
                message="Provider down",
            )
        ]
        
        mock_response = Mock()
        
        response = await readiness_probe_get_method(response=mock_response)
        
        assert response.ready is False
        assert "Configuration error: Critical failure" in response.reason
        # Provider health should not have been checked since config failed
        mock_get_providers_health_statuses.assert_not_called()

    @pytest.mark.asyncio  
    async def test_readiness_checks_providers_when_config_ok(self, mocker):
        """Test that provider health is checked when config/init are OK."""
        # Configuration/init check passes
        mock_comprehensive_readiness = mocker.patch(
            "app.endpoints.health.check_comprehensive_readiness"
        )
        mock_comprehensive_readiness.return_value = (True, "")
        
        # Provider check fails
        mock_get_providers_health_statuses = mocker.patch(
            "app.endpoints.health.get_providers_health_statuses"
        )
        mock_get_providers_health_statuses.return_value = [
            ProviderHealthStatus(
                provider_id="failing_provider",
                status=HealthStatus.ERROR.value,
                message="Provider connection failed",
            )
        ]
        
        mock_response = Mock()
        
        response = await readiness_probe_get_method(response=mock_response)
        
        assert response.ready is False
        assert "Unhealthy providers:" in response.reason
        assert "failing_provider" in response.reason
        # Provider health should have been checked
        mock_get_providers_health_statuses.assert_called_once()
