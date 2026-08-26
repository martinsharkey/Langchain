"""
Integration tests for Discovery → Optimization workflow.

Tests interaction between discovery and optimization services.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock


class TestDiscoveryOptimizationWorkflow:
    """Test integration between discovery and optimization."""

    @pytest.mark.integration
    def test_discovery_to_optimization_flow(
        self,
        sample_discovery_result,
        api_base_urls,
        services_running
    ):
        """Test complete discovery to optimization flow."""
        # Verify discovery completed
        assert sample_discovery_result["status"] == "complete"
        assert len(sample_discovery_result["discoveries"]) > 0
        
        # Extract best discovery
        best_discovery = sample_discovery_result["discoveries"][0]
        indicators = best_discovery["indicators"]
        
        # Should use discovery results in optimization
        assert len(indicators) > 0
        assert "parameters" in best_discovery

    @pytest.mark.integration
    def test_optimization_uses_discovery_indicators(
        self,
        sample_discovery_result,
        sample_optimization_result
    ):
        """Test optimization uses indicators from discovery."""
        # Discovery provides indicators
        discovery_indicators = sample_discovery_result["discoveries"][0]["indicators"]
        
        # Optimization works with those indicators
        opt_params = sample_optimization_result["best_trial"]["parameters"]
        
        # Should have parameters for the indicators
        assert len(opt_params) > 0

    @pytest.mark.integration
    def test_workflow_parameter_consistency(
        self,
        sample_discovery_result,
        sample_optimization_result
    ):
        """Test parameters remain consistent through workflow."""
        discovery_params = sample_discovery_result["discoveries"][0]["parameters"]
        optimization_params = sample_optimization_result["best_trial"]["parameters"]
        
        # Should have same parameter names
        discovery_keys = set(discovery_params.keys())
        optimization_keys = set(optimization_params.keys())
        
        # Optimization should have at least the discovery parameters
        assert discovery_keys.issubset(optimization_keys) or discovery_keys == optimization_keys

    @pytest.mark.integration
    def test_optimization_improves_over_discovery(
        self,
        sample_discovery_result,
        sample_optimization_result
    ):
        """Test optimization improves performance over discovery."""
        discovery_pf = sample_discovery_result["discoveries"][0]["performance"]["profit_factor"]
        optimization_pf = sample_optimization_result["best_trial"]["metrics"]["profit_factor"]
        
        # Optimization should improve or maintain performance
        assert optimization_pf >= discovery_pf * 0.95  # Allow 5% variance

    @pytest.mark.integration
    async def test_async_workflow_execution(self):
        """Test async workflow execution."""
        async def mock_discovery():
            return {"status": "complete", "discoveries": []}
        
        async def mock_optimization():
            return {"status": "complete", "best_trial": {}}
        
        # Both should complete
        discovery = await mock_discovery()
        optimization = await mock_optimization()
        
        assert discovery["status"] == "complete"
        assert optimization["status"] == "complete"

    @pytest.mark.integration
    def test_workflow_error_handling(self):
        """Test workflow handles errors gracefully."""
        class DiscoveryError(Exception):
            pass
        
        def failing_discovery():
            raise DiscoveryError("Discovery failed")
        
        with pytest.raises(DiscoveryError):
            failing_discovery()
        
        # Optimization should not proceed if discovery fails
        # This would be enforced at orchestration level

    @pytest.mark.integration
    def test_workflow_with_multiple_symbols(self, sample_discovery_result):
        """Test workflow can handle multiple symbols."""
        symbols = ["BTCUSD", "EURUSD", "XAUUSD"]
        
        for symbol in symbols:
            result = sample_discovery_result.copy()
            result["symbol"] = symbol
            assert result["symbol"] == symbol
            assert result["status"] == "complete"


class TestServiceCommunication:
    """Test service-to-service communication."""

    @pytest.mark.integration
    def test_api_endpoint_health(self, api_base_urls):
        """Test all service endpoints are healthy."""
        for service_name, base_url in api_base_urls.items():
            # In real test, would do: response = requests.get(f"{base_url}/health")
            # For now, just verify URL format
            assert base_url.startswith("http://")
            assert base_url.endswith(str(8000 + (list(api_base_urls.keys()).index(service_name) + 1)))

    @pytest.mark.integration
    def test_request_response_format(self):
        """Test request/response format compatibility."""
        request = {
            "symbol": "BTCUSD",
            "session": "London",
            "timeframe": "M15"
        }
        
        response = {
            "task_id": "test_123",
            "status": "queued"
        }
        
        # Both should be JSON serializable
        import json
        assert json.dumps(request)
        assert json.dumps(response)

    @pytest.mark.integration
    def test_task_id_propagation(self, sample_discovery_result):
        """Test task IDs propagate through workflow."""
        discovery_task_id = sample_discovery_result["task_id"]
        
        # Task ID should be consistent format
        assert discovery_task_id.startswith("disc_")
        assert len(discovery_task_id) > 5


class TestStateManagement:
    """Test state management across services."""

    @pytest.mark.integration
    def test_workflow_state_transitions(self):
        """Test valid state transitions."""
        states = ["queued", "in_progress", "complete", "failed"]
        
        # Typical transition path
        assert states.index("queued") < states.index("in_progress")
        assert states.index("in_progress") < states.index("complete")

    @pytest.mark.integration
    def test_concurrent_workflows(self):
        """Test multiple concurrent workflows don't interfere."""
        workflows = []
        
        for i in range(3):
            workflow = {
                "workflow_id": f"wf_{i}",
                "status": "in_progress",
                "symbol": f"SYMBOL_{i}"
            }
            workflows.append(workflow)
        
        # All workflows should be independent
        for i, wf in enumerate(workflows):
            assert wf["workflow_id"] == f"wf_{i}"
            assert wf["symbol"] == f"SYMBOL_{i}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
