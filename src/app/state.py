"""
Application State Tracking
=========================

This module provides application state tracking functionality for monitoring
initialization progress and health status. It's deliberately dependency-free
to avoid circular import issues.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger("app.state")


class ApplicationState:
    """Track application initialization state for readiness reporting."""
    
    def __init__(self):
        self._initialization_complete = False
        self._initialization_errors: List[str] = []
        self._startup_checks: Dict[str, bool] = {
            'configuration_loaded': False,
            'configuration_valid': False,
            'llama_client_initialized': False,
            'mcp_servers_registered': False
        }

    def mark_check_complete(self, check_name: str, success: bool, error_message: str = None):
        """Mark a startup check as complete."""
        if check_name in self._startup_checks:
            self._startup_checks[check_name] = success
            if success:
                logger.info("Initialization check passed: %s", check_name)
            else:
                if error_message:
                    self._initialization_errors.append(f"{check_name}: {error_message}")
                    logger.error("Initialization check failed: %s: %s", check_name, error_message)
                else:
                    logger.error("Initialization check failed: %s", check_name)
        else:
            logger.warning("Unknown startup check: %s", check_name)

    def mark_initialization_complete(self):
        """Mark the entire initialization as complete."""
        self._initialization_complete = True
        logger.info("Application initialization marked as complete")
    
    @property
    def is_fully_initialized(self) -> bool:
        """Check if application is fully initialized and ready."""
        return self._initialization_complete and all(self._startup_checks.values())
    
    @property
    def initialization_status(self) -> Dict[str, Any]:
        """Get detailed initialization status."""
        return {
            'complete': self._initialization_complete,
            'checks': self._startup_checks.copy(),
            'errors': self._initialization_errors.copy()
        }


# Global application state instance
app_state = ApplicationState()
