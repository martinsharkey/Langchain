"""
StrategyOps V2.0 - Full Stack Integration Tests

Tests the complete workflow from discovery through deployment and execution.
"""

import pytest
import asyncio
import json
from datetime import datetime
import requests

BASE_URL = "http://localhost:8000"
DISCOVERY_URL = f"{BASE_URL}/api/v1/discovery"
OPTIMIZATION_URL = f"{BASE_URL}/api/v1/optimization"
VALIDATION_URL = f"{BASE_URL}/api/v1/validation"
DEPLOYMENT_URL = f"{BASE_URL}/api/v1/deployment"
ORCHESTRATION_URL = f"{BASE_URL}/api/v1/orchestration"
EXECUTION_URL = f"{BASE_URL}/api/v1/execution"
AUTH_URL = f"{BASE_URL}/api/v1/auth"


class TestAPIGateway:
    """Test API Gateway routing."""
    
    def test_gateway_health(self):
        """Test gateway health check."""
        response = requests.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        assert "gateway" in response.text.lower() or "status" in response.text.lower()
    
    def test_discovery_routing(self):
        """Test gateway routes to discovery service."""
        response = requests.get(f"{DISCOVERY_URL}/strategies")
        assert response.status_code == 200
    
    def test_optimization_routing(self):
        """Test gateway routes to optimization service."""
        response = requests.get(f"{OPTIMIZATION_URL}")
        # May return 404 but should not be gateway error
        assert response.status_code in [200, 404, 405]
    
    def test_validation_routing(self):
        """Test gateway routes to validation service."""
        response = requests.get(f"{VALIDATION_URL}/rules")
        assert response.status_code == 200
    
    def test_deployment_routing(self):
        """Test gateway routes to deployment service."""
        response = requests.get(f"{DEPLOYMENT_URL}/strategies")
        assert response.status_code == 200
    
    def test_orchestration_routing(self):
        """Test gateway routes to orchestration service."""
        response = requests.get(f"{ORCHESTRATION_URL}/workflows")
        assert response.status_code == 200
    
    def test_execution_routing(self):
        """Test gateway routes to execution service."""
        response = requests.get(f"{EXECUTION_URL}/trades")
        assert response.status_code == 200


class TestAuthenticationFlow:
    """Test authentication and authorization."""
    
    def test_user_registration(self):
        """Test user registration."""
        response = requests.post(
            f"{AUTH_URL}/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "testpass123"
            }
        )
        assert response.status_code in [201, 200]
        data = response.json()
        assert "user_id" in data or "username" in data
    
    def test_user_login(self):
        """Test user login and token generation."""
        response = requests.post(
            f"{AUTH_URL}/login",
            json={
                "username": "admin",
                "password": "admin123"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data or "token" in data
    
    def test_token_verification(self):
        """Test token verification."""
        # First get a token
        login_response = requests.post(
            f"{AUTH_URL}/login",
            json={"username": "admin", "password": "admin123"}
        )
        
        if login_response.status_code == 200:
            token = login_response.json().get("access_token", "test_token")
            
            # Verify token
            response = requests.post(
                f"{AUTH_URL}/verify",
                headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200


class TestDiscoveryService:
    """Test discovery service functionality."""
    
    def test_list_strategies(self):
        """Test listing available strategies."""
        response = requests.get(f"{DISCOVERY_URL}/strategies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("strategies"), list)
    
    def test_start_discovery(self):
        """Test starting discovery job."""
        response = requests.post(
            f"{DISCOVERY_URL}/start",
            json={
                "job_id": "disc_test_001",
                "symbol": "XAUUSD",
                "timeframe": "M15",
                "session": "london",
                "entry_floors": {"london": 0.6}
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data or "status" in data
    
    def test_discovery_status(self):
        """Test getting discovery job status."""
        # Start discovery first
        start_response = requests.post(
            f"{DISCOVERY_URL}/start",
            json={
                "job_id": "disc_test_002",
                "symbol": "EURUSD",
                "timeframe": "M30",
                "session": "newyork",
                "entry_floors": {"newyork": 0.7}
            }
        )
        
        if start_response.status_code == 200:
            job_id = start_response.json().get("job_id", "disc_test_002")
            
            # Check status
            response = requests.get(f"{DISCOVERY_URL}/{job_id}/status")
            assert response.status_code == 200


class TestOptimizationService:
    """Test optimization service functionality."""
    
    def test_start_optimization(self):
        """Test starting optimization job."""
        response = requests.post(
            f"{OPTIMIZATION_URL}/start",
            json={
                "job_id": "optim_test_001",
                "symbol": "XAUUSD",
                "strategy_name": "RSI14",
                "session": "london",
                "timeframe": "M15"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data or "status" in data
    
    def test_optimization_status(self):
        """Test getting optimization status."""
        response = requests.get(f"{OPTIMIZATION_URL}/optim_test_001/status")
        # Should return 200 or 404
        assert response.status_code in [200, 404]


class TestValidationService:
    """Test validation service functionality."""
    
    def test_get_validation_rules(self):
        """Test getting validation rules."""
        response = requests.get(f"{VALIDATION_URL}/rules")
        assert response.status_code == 200
        data = response.json()
        assert "validation_rules" in data or "rules" in data
    
    def test_start_validation(self):
        """Test starting validation job."""
        response = requests.post(
            f"{VALIDATION_URL}/start",
            json={
                "job_id": "val_test_001",
                "symbol": "XAUUSD",
                "strategy_name": "RSI14",
                "session": "london"
            }
        )
        assert response.status_code == 200


class TestDeploymentService:
    """Test deployment service functionality."""
    
    def test_list_deployed_strategies(self):
        """Test listing deployed strategies."""
        response = requests.get(f"{DEPLOYMENT_URL}/strategies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("strategies"), list)
    
    def test_deploy_strategy(self):
        """Test deploying strategy."""
        response = requests.post(
            f"{DEPLOYMENT_URL}/deploy",
            json={
                "job_id": "deploy_test_001",
                "strategy_id": "strat_001",
                "strategy_name": "RSI14",
                "symbol": "XAUUSD",
                "session": "london",
                "floor_value": 0.65
            }
        )
        assert response.status_code == 200


class TestOrchestrationService:
    """Test orchestration service functionality."""
    
    def test_create_workflow(self):
        """Test creating workflow."""
        response = requests.post(
            f"{ORCHESTRATION_URL}/workflow/create",
            json={
                "workflow_id": "wf_test_001",
                "symbol": "XAUUSD",
                "timeframe": "M15",
                "session": "london"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "workflow_id" in data or "status" in data
    
    def test_list_workflows(self):
        """Test listing workflows."""
        response = requests.get(f"{ORCHESTRATION_URL}/workflows")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("workflows"), list)


class TestExecutionService:
    """Test execution service functionality."""
    
    def test_list_trades(self):
        """Test listing trades."""
        response = requests.get(f"{EXECUTION_URL}/trades")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("trades"), list)
    
    def test_open_trade(self):
        """Test opening trade."""
        response = requests.post(
            f"{EXECUTION_URL}/trade/open",
            json={
                "trade_id": "trade_test_001",
                "symbol": "XAUUSD",
                "direction": "long",
                "size": 0.1,
                "entry_price": 2000.0,
                "stop_loss": 1990.0,
                "take_profit": 2020.0
            }
        )
        assert response.status_code == 200


class TestEndToEndWorkflow:
    """Test complete workflow integration."""
    
    @pytest.mark.integration
    def test_complete_discovery_to_deployment_workflow(self):
        """Test complete workflow from discovery to deployment."""
        workflow_data = {
            "workflow_id": "e2e_test_001",
            "symbol": "XAUUSD",
            "timeframe": "M15",
            "session": "london"
        }
        
        # 1. Create workflow
        wf_response = requests.post(
            f"{ORCHESTRATION_URL}/workflow/create",
            json=workflow_data
        )
        assert wf_response.status_code == 200
        workflow_id = wf_response.json().get("workflow_id", workflow_data["workflow_id"])
        
        # 2. Start discovery
        disc_response = requests.post(
            f"{DISCOVERY_URL}/start",
            json={
                "job_id": f"disc_{workflow_id}",
                "symbol": workflow_data["symbol"],
                "timeframe": workflow_data["timeframe"],
                "session": workflow_data["session"],
                "entry_floors": {workflow_data["session"]: 0.6}
            }
        )
        assert disc_response.status_code == 200
        
        # 3. Start optimization
        optim_response = requests.post(
            f"{OPTIMIZATION_URL}/start",
            json={
                "job_id": f"optim_{workflow_id}",
                "symbol": workflow_data["symbol"],
                "strategy_name": "RSI14",
                "session": workflow_data["session"],
                "timeframe": workflow_data["timeframe"]
            }
        )
        assert optim_response.status_code == 200
        
        # 4. Start validation
        val_response = requests.post(
            f"{VALIDATION_URL}/start",
            json={
                "job_id": f"val_{workflow_id}",
                "symbol": workflow_data["symbol"],
                "strategy_name": "RSI14",
                "session": workflow_data["session"]
            }
        )
        assert val_response.status_code == 200
        
        # 5. Deploy strategy
        deploy_response = requests.post(
            f"{DEPLOYMENT_URL}/deploy",
            json={
                "job_id": f"deploy_{workflow_id}",
                "strategy_id": f"strat_{workflow_id}",
                "strategy_name": "RSI14",
                "symbol": workflow_data["symbol"],
                "session": workflow_data["session"],
                "floor_value": 0.65
            }
        )
        assert deploy_response.status_code == 200
        
        # 6. Get workflow status
        status_response = requests.get(
            f"{ORCHESTRATION_URL}/workflow/{workflow_id}/status"
        )
        assert status_response.status_code == 200


class TestHealthChecks:
    """Test all service health checks."""
    
    def test_discovery_health(self):
        """Test discovery service health."""
        response = requests.get(f"http://localhost:8001/health")
        assert response.status_code == 200
    
    def test_optimization_health(self):
        """Test optimization service health."""
        response = requests.get(f"http://localhost:8002/health")
        assert response.status_code == 200
    
    def test_validation_health(self):
        """Test validation service health."""
        response = requests.get(f"http://localhost:8003/health")
        assert response.status_code == 200
    
    def test_deployment_health(self):
        """Test deployment service health."""
        response = requests.get(f"http://localhost:8004/health")
        assert response.status_code == 200
    
    def test_orchestration_health(self):
        """Test orchestration service health."""
        response = requests.get(f"http://localhost:8005/health")
        assert response.status_code == 200
    
    def test_execution_health(self):
        """Test execution service health."""
        response = requests.get(f"http://localhost:8006/health")
        assert response.status_code == 200
    
    def test_auth_health(self):
        """Test auth service health."""
        response = requests.get(f"http://localhost:8007/health")
        assert response.status_code == 200


class TestPerformance:
    """Test system performance."""
    
    def test_response_time_under_threshold(self):
        """Test that responses are fast."""
        import time
        
        start = time.time()
        response = requests.get(f"{DISCOVERY_URL}/strategies")
        duration = time.time() - start
        
        assert response.status_code == 200
        assert duration < 1.0  # Should respond in under 1 second
    
    def test_concurrent_requests(self):
        """Test handling concurrent requests."""
        import concurrent.futures
        
        def make_request():
            return requests.get(f"{DISCOVERY_URL}/strategies")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        assert all(r.status_code == 200 for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
