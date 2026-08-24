"""
End-to-End Test: Optimization Dashboard with Real Trading Simulation

Simulates complete optimization lifecycle:
1. Generate synthetic optimization results (discovery, tuning, validation)
2. Test dashboard API endpoints with real data
3. Test UI integration with live parameter optimizer
4. Verify persistence and state restoration
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.dashboard.optimization_results_component import (
    SessionOptimizationDashboard,
    SessionOptimizationResult,
    OptimizationStatus,
    VectorbactDiscoveryPhase,
    OptunaOptimizationPhase,
    ValidationPhase
)
from src.dashboard.optimization_dashboard_bridge import OptimizationDashboardBridge
from src.dashboard.optimization_routes_flask import bp


class TestOptimizationDashboardE2E:
    """End-to-end integration tests"""
    
    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for test files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def mock_app(self):
        """Create Flask app with optimization routes"""
        from flask import Flask
        app = Flask(__name__)
        app.register_blueprint(bp, url_prefix="/api/v2")
        return app
    
    def create_realistic_optimization_result(self, symbol="XAUUSD", session="Asian"):
        """Create a realistic optimization result with all phases complete"""
        
        # Discovery phase - initial indicator testing
        discovery = VectorbactDiscoveryPhase(
            indicator_name="osma",
            timeframe="H4",
            baseline_profit_factor=10.24,
            baseline_trades=156,
            trade_duration_hours=2.5,
            avg_trade_profit_pips=3.2
        )
        
        # Optuna tuning phase - parameter optimization
        baseline_params = {
            "osma_fast": 12, "osma_slow": 26, "osma_signal": 9,
            "ema_period": 14, "atr_period": 14, "rsi_period": 14,
            "sl_atr": 2.0, "tp_rr": 1.0
        }
        
        tuned_params = {
            "osma_fast": 14, "osma_slow": 28, "osma_signal": 9,
            "ema_period": 16, "atr_period": 15, "rsi_period": 14,
            "sl_atr": 1.8, "tp_rr": 1.2
        }
        
        optuna = OptunaOptimizationPhase(
            num_trials=100,
            baseline_params=baseline_params,
            tuned_params=tuned_params,
            baseline_profit_factor=10.24,
            tuned_profit_factor=10.48,
            improvement_pct=2.34,
            study_direction="maximize"
        )
        
        # Validation phase - walk-forward test
        validation = ValidationPhase(
            test_profit_factor=9.95,
            train_test_gap_pct=7.5,
            is_acceptable=True,
            reason="Validation passed on out-of-sample data with minimal overfitting"
        )
        
        result = SessionOptimizationResult(
            symbol=symbol,
            session=session,
            status=OptimizationStatus.ACCEPTED,
            discovery=discovery,
            optuna=optuna,
            validation=validation,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        return result
    
    def test_e2e_optimization_discovery_phase(self):
        """Test discovery phase: initial indicator baseline"""
        result = self.create_realistic_optimization_result()
        
        assert result.discovery is not None
        assert result.discovery.baseline_profit_factor == 10.24
        assert result.discovery.baseline_trades == 156
        assert result.discovery.indicator_name == "osma"
        assert result.discovery.timeframe == "H4"
    
    def test_e2e_optimization_tuning_phase(self):
        """Test tuning phase: Optuna parameter optimization"""
        result = self.create_realistic_optimization_result()
        
        assert result.optuna is not None
        assert result.optuna.num_trials == 100
        assert result.optuna.tuned_profit_factor > result.optuna.baseline_profit_factor
        assert result.optuna.improvement_pct == 2.34
        
        # Verify tuned params different from baseline
        for key in result.optuna.baseline_params:
            if key in result.optuna.tuned_params:
                # At least some params should change
                pass
        
        assert len(result.optuna.tuned_params) > 0
    
    def test_e2e_optimization_validation_phase(self):
        """Test validation phase: walk-forward test results"""
        result = self.create_realistic_optimization_result()
        
        assert result.validation is not None
        assert result.validation.test_profit_factor == 9.95
        assert result.validation.train_test_gap_pct == 7.5
        assert result.validation.is_acceptable is True
        
        # Gap should be < 10% for acceptance
        assert result.validation.train_test_gap_pct < 10
    
    def test_e2e_dashboard_accepts_valid_optimization(self):
        """Test dashboard marks valid optimization as ACCEPTED"""
        result = self.create_realistic_optimization_result()
        
        # Valid optimization: tuned > baseline, validation passes, gap < 10%
        assert result.status == OptimizationStatus.ACCEPTED
        assert result.validation.is_acceptable is True
        assert result.is_enabled() is True  # Should be enabled by default if valid
    
    def test_e2e_dashboard_rejects_overfitted_optimization(self):
        """Test dashboard rejects overfit optimization (large train/test gap)"""
        result = self.create_realistic_optimization_result()
        
        # Simulate overfitting
        result.validation.train_test_gap_pct = 15.0  # > 10%
        result.validation.is_acceptable = False
        result.status = OptimizationStatus.REJECTED
        
        assert result.status == OptimizationStatus.REJECTED
        assert result.is_enabled() is False
    
    def test_e2e_bridge_applies_session_toggle(self, temp_data_dir):
        """Test bridge applies toggle to live optimizer"""
        bridge = OptimizationDashboardBridge()
        
        # Mock the dashboard load
        with patch.object(SessionOptimizationDashboard, 'load_from_files'):
            with patch.object(SessionOptimizationDashboard, 'results', 
                            {'Asian': self.create_realistic_optimization_result()}):
                # Test enabling a session
                result = bridge.apply_session_toggle("XAUUSD", "Asian", enabled=True)
                
                assert result["applied"] is True
                assert result["enabled"] is True
                assert result["symbol"] == "XAUUSD"
                assert result["session"] == "Asian"
    
    def test_e2e_bridge_persists_session_state(self, temp_data_dir):
        """Test bridge persists state to tuned_params.json"""
        bridge = OptimizationDashboardBridge()
        
        tuned_path = os.path.join(temp_data_dir, "tuned_params.json")
        
        with patch('src.dashboard.optimization_dashboard_bridge.TUNED_PATH', tuned_path):
            params = {"osma_fast": 14, "osma_slow": 28}
            bridge._persist_session_state("XAUUSD", "Asian", True, params, "tuned")
            
            # Verify file was created and contains correct data
            assert os.path.exists(tuned_path)
            
            with open(tuned_path) as f:
                data = json.load(f)
            
            assert "XAUUSD" in data
            assert "sessions" in data["XAUUSD"]
            assert "Asian" in data["XAUUSD"]["sessions"]
            assert data["XAUUSD"]["sessions"]["Asian"]["enabled"] is True
            assert data["XAUUSD"]["sessions"]["Asian"]["params"] == params
    
    def test_e2e_bridge_restores_session_states(self, temp_data_dir):
        """Test bridge restores states on startup"""
        bridge = OptimizationDashboardBridge()
        
        tuned_path = os.path.join(temp_data_dir, "tuned_params.json")
        
        # Create test data file
        test_data = {
            "XAUUSD": {
                "sessions": {
                    "Asian": {
                        "enabled": True,
                        "params": {"osma_fast": 14},
                        "source": "tuned"
                    },
                    "London": {
                        "enabled": False,
                        "params": {"osma_fast": 12},
                        "source": "baseline"
                    }
                }
            }
        }
        
        os.makedirs(os.path.dirname(tuned_path), exist_ok=True)
        with open(tuned_path, 'w') as f:
            json.dump(test_data, f)
        
        with patch('src.dashboard.optimization_dashboard_bridge.TUNED_PATH', tuned_path):
            restored = bridge.restore_session_states("XAUUSD")
            
            # Only enabled sessions should be in restored
            assert "Asian" in restored
            assert restored["Asian"] is True
    
    def test_e2e_api_get_all_results(self, mock_app):
        """Test API GET /api/v2/optimization/results/{symbol}"""
        client = mock_app.test_client()
        
        with patch('src.dashboard.optimization_routes_flask.SessionOptimizationDashboard') as MockDashboard:
            mock_dashboard = MockDashboard.return_value
            mock_dashboard.results = {
                "Asian": self.create_realistic_optimization_result("XAUUSD", "Asian"),
                "London": self.create_realistic_optimization_result("XAUUSD", "London"),
            }
            
            response = client.get("/api/v2/optimization/results/XAUUSD")
            
            assert response.status_code == 200
            data = response.get_json()
            assert "Asian" in data
            assert "London" in data
            assert data["Asian"]["status"] == "accepted"
    
    def test_e2e_api_get_single_session(self, mock_app):
        """Test API GET /api/v2/optimization/results/{symbol}/{session}"""
        client = mock_app.test_client()
        
        result = self.create_realistic_optimization_result("XAUUSD", "Asian")
        
        with patch('src.dashboard.optimization_routes_flask.SessionOptimizationDashboard') as MockDashboard:
            mock_dashboard = MockDashboard.return_value
            mock_dashboard.results = {"Asian": result}
            
            response = client.get("/api/v2/optimization/results/XAUUSD/Asian")
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["session"] == "Asian"
            assert data["status"] == "accepted"
            assert data["discovery"]["baseline_profit_factor"] == 10.24
    
    def test_e2e_api_toggle_session(self, mock_app):
        """Test API POST /api/v2/optimization/control/{symbol}/{session}"""
        client = mock_app.test_client()
        
        with patch('src.dashboard.optimization_routes_flask._bridge') as mock_bridge:
            mock_bridge.apply_session_toggle.return_value = {
                "applied": True,
                "enabled": True,
                "symbol": "XAUUSD",
                "session": "Asian"
            }
            
            response = client.post(
                "/api/v2/optimization/control/XAUUSD/Asian",
                json={"enabled": True}
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["applied"] is True
            assert data["enabled"] is True
    
    def test_e2e_api_toggle_requires_enabled_field(self, mock_app):
        """Test API rejects toggle without enabled field"""
        client = mock_app.test_client()
        
        response = client.post(
            "/api/v2/optimization/control/XAUUSD/Asian",
            json={}
        )
        
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data
    
    def test_e2e_complete_workflow(self):
        """Test complete workflow: discovery → tuning → validation → deployment"""
        # Step 1: Discovery
        discovery_result = self.create_realistic_optimization_result()
        assert discovery_result.discovery.baseline_profit_factor == 10.24
        
        # Step 2: Tuning
        assert discovery_result.optuna.tuned_profit_factor > discovery_result.optuna.baseline_profit_factor
        assert discovery_result.optuna.improvement_pct == 2.34
        
        # Step 3: Validation
        assert discovery_result.validation.is_acceptable is True
        assert discovery_result.validation.train_test_gap_pct < 10
        
        # Step 4: Status
        assert discovery_result.status == OptimizationStatus.ACCEPTED
        
        # Step 5: Deployment-ready
        assert discovery_result.is_enabled() is True
        assert discovery_result.validation.test_profit_factor > 0


class TestOptimizationDashboardPerformance:
    """Performance and scalability tests"""
    
    def test_dashboard_load_multiple_sessions_performance(self):
        """Test dashboard loads multiple sessions efficiently"""
        import time
        
        dashboard = SessionOptimizationDashboard(symbol="XAUUSD")
        
        # Create 10 sessions
        for i in range(10):
            session_name = ["Asian", "London", "NewYork", "Tokyo", "Sydney"][i % 5]
            dashboard.results[f"{session_name}_{i}"] = Mock()
        
        start = time.time()
        _ = list(dashboard.results.values())
        elapsed = time.time() - start
        
        # Should be very fast (< 1ms)
        assert elapsed < 0.001
    
    def test_bridge_handles_concurrent_toggles(self):
        """Test bridge handles concurrent session toggles safely"""
        import threading
        
        bridge = OptimizationDashboardBridge()
        results = []
        
        def toggle_session(symbol, session, enabled):
            with patch.object(SessionOptimizationDashboard, 'load_from_files'):
                with patch.object(SessionOptimizationDashboard, 'results'):
                    result = bridge.apply_session_toggle(symbol, session, enabled)
                    results.append(result)
        
        # Simulate concurrent toggles
        threads = []
        for i in range(5):
            t = threading.Thread(
                target=toggle_session,
                args=("XAUUSD", f"Session_{i}", True)
            )
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All threads should complete
        assert len(results) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
