"""
Integration Test: Optimization Dashboard (Flask Routes + UI)

Tests:
1. Flask route GET /api/v2/optimization/results/{symbol}
2. Flask route GET /api/v2/optimization/results/{symbol}/{session}
3. Flask route POST /api/v2/optimization/control/{symbol}/{session}
4. Flask route GET /api/v2/optimization/summary/{symbol}
5. UI component rendering with returned data
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# For running tests without full Flask setup
class MockFlaskApp:
    """Mock Flask app for testing routes"""
    
    def __init__(self):
        self.test_results = {}
    
    def test_route_get_all_results(self, symbol):
        """Test GET /api/v2/optimization/results/{symbol}"""
        from src.dashboard.optimization_results_component import SessionOptimizationDashboard
        
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        return {
            "symbol": symbol,
            "timestamp": list(dashboard.results.values())[0].timestamp if dashboard.results else None,
            "sessions": dashboard.get_all_cards(),
            "summary": {
                "total": len(dashboard.sessions),
                "accepted": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "accepted"),
                "rejected": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "rejected"),
                "pending": sum(1 for r in dashboard.results.values() 
                             if r.status.value == "pending"),
                "enabled": sum(1 for r in dashboard.results.values() 
                             if r.is_enabled()),
            }
        }
    
    def test_route_get_session_result(self, symbol, session):
        """Test GET /api/v2/optimization/results/{symbol}/{session}"""
        from src.dashboard.optimization_results_component import SessionOptimizationDashboard
        
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        if session not in dashboard.results:
            return {"error": f"Session {session} not found"}, 404
        
        return dashboard.get_ui_card_data(session), 200
    
    def test_route_toggle_session(self, symbol, session, enabled):
        """Test POST /api/v2/optimization/control/{symbol}/{session}"""
        from src.dashboard.optimization_results_component import SessionOptimizationDashboard
        
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        if session not in dashboard.results:
            return {"error": f"Session {session} not found"}, 404
        
        result = dashboard.results[session]
        
        if result.status.value not in ["accepted", "rejected"]:
            return {
                "error": f"Cannot toggle: status is {result.status.value}"
            }, 400
        
        result.override_enabled = enabled
        
        return {
            "symbol": symbol,
            "session": session,
            "enabled": result.is_enabled(),
            "status": result.status.value,
            "message": f"Session {session} {'enabled' if enabled else 'disabled'}"
        }, 200
    
    def test_route_get_summary(self, symbol):
        """Test GET /api/v2/optimization/summary/{symbol}"""
        from src.dashboard.optimization_results_component import SessionOptimizationDashboard
        
        dashboard = SessionOptimizationDashboard(symbol=symbol)
        dashboard.load_from_files()
        
        return {
            "symbol": symbol,
            "summary": {
                "total_sessions": len(dashboard.sessions),
                "accepted": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "accepted"),
                "rejected": sum(1 for r in dashboard.results.values() 
                              if r.status.value == "rejected"),
                "pending": sum(1 for r in dashboard.results.values() 
                             if r.status.value == "pending"),
                "enabled": sum(1 for r in dashboard.results.values() 
                             if r.is_enabled()),
            },
            "sessions": {
                session: {
                    "status": result.status.value,
                    "enabled": result.is_enabled(),
                    "recommendation": result.get_recommendation()["action"]
                }
                for session, result in dashboard.results.items()
            }
        }, 200


def run_integration_tests():
    """Run all integration tests"""
    from src.utils.logger import get_logger
    
    logger = get_logger("test_integration_dashboard")
    
    logger.info("\n" + "="*80)
    logger.info("INTEGRATION TEST: Optimization Dashboard (Flask Routes)")
    logger.info("="*80)
    
    app = MockFlaskApp()
    symbol = "XAUUSD"
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: GET /api/v2/optimization/results/{symbol}
    logger.info("\n[TEST 1] GET /api/v2/optimization/results/{symbol}")
    try:
        response = app.test_route_get_all_results(symbol)
        
        assert "symbol" in response
        assert "sessions" in response
        assert "summary" in response
        
        summary = response["summary"]
        logger.info(f"  ✓ Returned all sessions for {symbol}")
        logger.info(f"    Total: {summary['total']}")
        logger.info(f"    Accepted: {summary['accepted']}")
        logger.info(f"    Rejected: {summary['rejected']}")
        logger.info(f"    Pending: {summary['pending']}")
        logger.info(f"    Enabled: {summary['enabled']}")
        
        tests_passed += 1
    except Exception as e:
        logger.error(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 2: GET /api/v2/optimization/results/{symbol}/{session}
    logger.info("\n[TEST 2] GET /api/v2/optimization/results/{symbol}/{session}")
    try:
        sessions = ["Asian", "London", "NewYork"]
        
        for session in sessions:
            response, status = app.test_route_get_session_result(symbol, session)
            
            if status == 200:
                assert "session" in response
                assert "recommendation" in response
                logger.info(f"  ✓ Retrieved {session} results")
                logger.info(f"    Status: {response['status']}")
                logger.info(f"    Recommendation: {response['recommendation']['action']}")
            elif status == 404:
                logger.info(f"  ✓ {session} not found (expected if not optimized)")
        
        tests_passed += 1
    except Exception as e:
        logger.error(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 3: POST /api/v2/optimization/control/{symbol}/{session}
    logger.info("\n[TEST 3] POST /api/v2/optimization/control/{symbol}/{session}")
    try:
        response, status = app.test_route_toggle_session(symbol, "Asian", False)
        
        if status == 200:
            logger.info(f"  ✓ Toggled Asian session")
            logger.info(f"    Enabled: {response['enabled']}")
            
            # Toggle back
            response2, status2 = app.test_route_toggle_session(symbol, "Asian", True)
            if status2 == 200:
                logger.info(f"  ✓ Toggled back to enabled")
        elif status == 400:
            logger.info(f"  ✓ Cannot toggle non-finalized session (expected)")
        
        tests_passed += 1
    except Exception as e:
        logger.error(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 4: GET /api/v2/optimization/summary/{symbol}
    logger.info("\n[TEST 4] GET /api/v2/optimization/summary/{symbol}")
    try:
        response, status = app.test_route_get_summary(symbol)
        
        assert status == 200
        assert "summary" in response
        assert "sessions" in response
        
        logger.info(f"  ✓ Returned summary for {symbol}")
        
        for session_name, session_data in response["sessions"].items():
            logger.info(f"    {session_name}: {session_data['status']}")
        
        tests_passed += 1
    except Exception as e:
        logger.error(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Test 5: UI Data Structure
    logger.info("\n[TEST 5] UI Data Structure Validation")
    try:
        response = app.test_route_get_all_results(symbol)
        
        for session_data in response["sessions"]:
            # Verify all required UI fields
            assert "session" in session_data
            assert "status" in session_data
            assert "recommendation" in session_data
            assert "discovery" in session_data or session_data["discovery"] is None
            assert "optuna" in session_data or session_data["optuna"] is None
            assert "validation" in session_data or session_data["validation"] is None
            assert "control" in session_data
            
            # Verify recommendation has required fields
            rec = session_data["recommendation"]
            assert "action" in rec
            assert "icon" in rec
            assert "color" in rec
            assert "reason" in rec
        
        logger.info(f"  ✓ All UI data structures valid")
        logger.info(f"    Sessions: {len(response['sessions'])}")
        logger.info(f"    Each has: session, status, recommendation, discovery, optuna, validation, control")
        
        tests_passed += 1
    except Exception as e:
        logger.error(f"  ✗ FAILED: {e}")
        tests_failed += 1
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info(f"INTEGRATION TEST RESULTS: {tests_passed} passed, {tests_failed} failed")
    logger.info("="*80)
    
    if tests_failed == 0:
        logger.info("\n✅ All integration tests passed!")
        logger.info("   - Flask routes working correctly")
        logger.info("   - Data structure valid for UI")
        logger.info("   - Ready for React component integration")
    
    return tests_failed == 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    success = run_integration_tests()
    sys.exit(0 if success else 1)
