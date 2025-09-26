"""Unit tests for the ApplicationState class."""

import pytest
from app.state import ApplicationState


class TestApplicationState:
    """Test cases for the ApplicationState class."""
    
    def test_initial_state(self):
        """Test that ApplicationState initializes with correct default values."""
        state = ApplicationState()
        
        assert state.is_fully_initialized is False
        
        status = state.initialization_status
        assert status['complete'] is False
        assert status['errors'] == []
        
        checks = status['checks']
        assert checks['configuration_loaded'] is False
        assert checks['configuration_valid'] is False 
        assert checks['llama_client_initialized'] is False
        assert checks['mcp_servers_registered'] is False

    def test_mark_check_complete_success(self):
        """Test marking initialization checks as complete."""
        state = ApplicationState()
        
        state.mark_check_complete('configuration_loaded', True)
        
        status = state.initialization_status
        checks = status['checks']
        assert checks['configuration_loaded'] is True
        assert checks['configuration_valid'] is False  # others unchanged
        assert status['errors'] == []

    def test_mark_check_complete_failure_with_message(self):
        """Test marking initialization checks as failed with error message."""
        state = ApplicationState()
        
        error_message = "Failed to load configuration: Invalid YAML"
        state.mark_check_complete('configuration_loaded', False, error_message)
        
        status = state.initialization_status
        checks = status['checks']
        assert checks['configuration_loaded'] is False
        assert len(status['errors']) == 1
        assert f"configuration_loaded: {error_message}" in status['errors'][0]

    def test_mark_check_complete_failure_with_exception(self):
        """Test marking initialization checks as failed with exception."""
        state = ApplicationState()
        
        error = ValueError("Invalid configuration format")
        state.mark_check_complete('llama_client_initialized', False, str(error))
        
        status = state.initialization_status
        checks = status['checks']
        assert checks['llama_client_initialized'] is False
        assert len(status['errors']) == 1
        assert "Invalid configuration format" in status['errors'][0]

    def test_mark_multiple_checks_complete(self):
        """Test marking multiple initialization checks as complete."""
        state = ApplicationState()
        
        state.mark_check_complete('configuration_loaded', True)
        state.mark_check_complete('configuration_valid', True)
        state.mark_check_complete('llama_client_initialized', True)
        
        status = state.initialization_status
        checks = status['checks']
        assert checks['configuration_loaded'] is True
        assert checks['configuration_valid'] is True
        assert checks['llama_client_initialized'] is True
        assert checks['mcp_servers_registered'] is False  # not set yet

    def test_mark_initialization_complete(self):
        """Test marking overall initialization as complete."""
        state = ApplicationState()
        
        # Mark all checks as complete
        state.mark_check_complete('configuration_loaded', True)
        state.mark_check_complete('configuration_valid', True)
        state.mark_check_complete('llama_client_initialized', True) 
        state.mark_check_complete('mcp_servers_registered', True)
        
        state.mark_initialization_complete()
        
        assert state.is_fully_initialized is True

    def test_is_fully_initialized_false_when_checks_incomplete(self):
        """Test that is_fully_initialized returns False when not all checks are complete."""
        state = ApplicationState()
        
        # Mark some but not all checks as complete
        state.mark_check_complete('configuration_loaded', True)
        state.mark_check_complete('configuration_valid', True)
        # Leave llama_client_initialized and mcp_servers_registered as False
        
        assert state.is_fully_initialized is False

    def test_is_fully_initialized_false_with_errors(self):
        """Test that is_fully_initialized returns False when there are errors."""
        state = ApplicationState()
        
        # Mark all checks as complete but with some errors
        state.mark_check_complete('configuration_loaded', True)
        state.mark_check_complete('configuration_valid', False, "Validation failed")
        state.mark_check_complete('llama_client_initialized', True)
        state.mark_check_complete('mcp_servers_registered', True)
        
        assert state.is_fully_initialized is False
        status = state.initialization_status
        assert len(status['errors']) == 1

    def test_accumulates_multiple_errors(self):
        """Test that multiple errors are accumulated correctly."""
        state = ApplicationState()
        
        state.mark_check_complete('configuration_loaded', False, "Config file not found")
        state.mark_check_complete('llama_client_initialized', False, "Connection timeout")
        
        status = state.initialization_status
        assert len(status['errors']) == 2
        error_text = ' '.join(status['errors'])
        assert "Config file not found" in error_text
        assert "Connection timeout" in error_text

    def test_invalid_check_name_ignored(self):
        """Test that invalid check names are ignored."""
        state = ApplicationState()
        
        # Should not raise an error, just be ignored
        state.mark_check_complete('invalid_check_name', True)
        
        # Check that valid checks still work
        state.mark_check_complete('configuration_loaded', True)
        status = state.initialization_status
        checks = status['checks']
        assert checks['configuration_loaded'] is True

    def test_mark_check_complete_with_none_error_message(self):
        """Test marking check as failed with None error message."""
        state = ApplicationState()
        
        state.mark_check_complete('configuration_loaded', False, None)
        
        status = state.initialization_status
        checks = status['checks']
        assert checks['configuration_loaded'] is False
        # Should not add any error message when None is provided
        assert status['errors'] == []

    def test_reset_functionality(self):
        """Test that state can be reset for testing purposes."""
        state = ApplicationState()
        
        # Set some state
        state.mark_check_complete('configuration_loaded', True)
        state.mark_check_complete('configuration_valid', False, "Error occurred")
        state.mark_initialization_complete()
        
        # Reset state manually (simulating what might happen in tests)
        state._initialization_complete = False
        state._initialization_errors = []
        state._startup_checks = {
            'configuration_loaded': False,
            'configuration_valid': False,
            'llama_client_initialized': False,
            'mcp_servers_registered': False
        }
        
        # Verify reset
        assert state.is_fully_initialized is False
        status = state.initialization_status
        assert status['errors'] == []
        checks = status['checks']
        assert all(not value for value in checks.values())

    def test_initialization_status_is_copy(self):
        """Test that initialization_status returns a copy, not the internal dict."""
        state = ApplicationState()
        
        status1 = state.initialization_status
        status2 = state.initialization_status
        
        # Should be equal but not the same object
        assert status1 == status2
        assert status1 is not status2
        
        # Modifying returned dict should not affect internal state
        status1['checks']['configuration_loaded'] = True
        status3 = state.initialization_status
        assert status3['checks']['configuration_loaded'] is False

    def test_initialization_errors_is_copy(self):
        """Test that initialization_errors returns a copy of the internal list."""
        state = ApplicationState()
        
        state.mark_check_complete('configuration_loaded', False, "Test error")
        
        status1 = state.initialization_status
        status2 = state.initialization_status
        errors1 = status1['errors']
        errors2 = status2['errors']
        
        # Should be equal but not the same object
        assert errors1 == errors2
        assert errors1 is not errors2
        
        # Modifying returned list should not affect internal state
        errors1.append("New error")
        status3 = state.initialization_status
        errors3 = status3['errors']
        assert len(errors3) == 1
        assert "New error" not in errors3
