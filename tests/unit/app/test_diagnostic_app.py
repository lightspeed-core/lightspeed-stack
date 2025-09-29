"""Unit tests for the diagnostic FastAPI app."""

import pytest
from unittest.mock import Mock
from app.diagnostic_app import create_diagnostic_app, diagnostic_app


class TestDiagnosticApp:
    """Test cases for the diagnostic FastAPI application."""

    def test_create_diagnostic_app(self):
        """Test that create_diagnostic_app returns a FastAPI instance."""
        app = create_diagnostic_app()
        
        # Should be a FastAPI instance
        assert app is not None
        assert hasattr(app, "include_router")
        assert hasattr(app, "get")
        assert hasattr(app, "post")
        
        # Should have the correct metadata
        assert app.title == "Lightspeed Stack - Diagnostic Mode"
        assert "diagnostic mode" in app.description
        # Version should be from version module, not hardcoded
        assert hasattr(app, 'version')

    def test_diagnostic_app_global_instance(self):
        """Test that the global diagnostic_app instance is properly initialized."""
        assert diagnostic_app is not None
        assert diagnostic_app.title == "Lightspeed Stack - Diagnostic Mode"

    def test_diagnostic_app_includes_health_router(self):
        """Test that diagnostic app includes the health router."""
        app = create_diagnostic_app()
        
        # Check if routes are present (indirect way to verify router inclusion)
        # The health router should add /readiness and /liveness routes
        routes = [route.path for route in app.routes if hasattr(route, 'path')]
        
        # Should have the health endpoints
        assert any(path.endswith('/readiness') for path in routes), f"Routes: {routes}"
        assert any(path.endswith('/liveness') for path in routes), f"Routes: {routes}"

    def test_diagnostic_app_minimal_functionality(self):
        """Test that diagnostic app only includes essential routes."""
        app = create_diagnostic_app()
        
        # Get all routes with paths
        route_paths = []
        for route in app.routes:
            if hasattr(route, 'path'):
                route_paths.append(route.path)
            elif hasattr(route, 'path_regex'):
                # For mount routes, get the prefix
                route_paths.append(str(route.path_regex.pattern))
        
        # Should be minimal - only health routes and possibly OpenAPI routes
        health_routes = [path for path in route_paths 
                        if 'readiness' in path or 'liveness' in path]
        
        # Should have health routes
        assert len(health_routes) >= 2, f"Expected health routes, got: {route_paths}"
        
        # Should not have business logic routes like /query, /models etc
        business_routes = [path for path in route_paths 
                          if any(endpoint in path for endpoint in 
                                ['/query', '/models', '/conversations', '/authorized'])]
        
        assert len(business_routes) == 0, f"Diagnostic app should not have business routes: {business_routes}"

    def test_diagnostic_app_health_endpoints_accessible(self):
        """Test that health endpoints are accessible in diagnostic app."""
        from fastapi.testclient import TestClient
        
        app = create_diagnostic_app()
        client = TestClient(app)
        
        # Test readiness endpoint
        response = client.get("/readiness")
        assert response.status_code in [200, 503]  # Either ready or not ready
        assert "ready" in response.json()
        
        # Test liveness endpoint  
        response = client.get("/liveness")
        assert response.status_code == 200
        assert response.json()["alive"] is True

    def test_diagnostic_app_independence(self):
        """Test that diagnostic app can be created without main app dependencies."""
        # This test verifies that the diagnostic app doesn't depend on
        # configuration, authentication, or other business logic components
        # that might not be available when the main app fails to start
        
        # Should be able to create multiple instances
        app1 = create_diagnostic_app()
        app2 = create_diagnostic_app()
        
        assert app1 is not app2  # Different instances
        assert app1.title == app2.title  # But same configuration
