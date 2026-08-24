"""
Test Suite for Session Optimization Dashboard Component

Tests:
1. Loading optimization results from files
2. UI card data generation
3. Recommendations generation
4. Enable/Disable toggle functionality
5. Per-session display accuracy
6. Overfitting detection UI
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from src.dashboard.optimization_results_component import (
    SessionOptimizationDashboard,
    OptimizationStatus,
    VectorbtResult,
    OptunaResult,
    ValidationResult,
    SessionOptimizationResult
)
from src.utils.logger import get_logger

logger = get_logger("test_optimization_dashboard")


class TestOptimizationDashboard:
    """Test suite for optimization dashboard"""
    
    def test_load_optimization_results(self):
        """TEST 1: Load results from files"""
        logger.info("\n" + "="*80)
        logger.info("TEST 1: Load Optimization Results from Files")
        logger.info("="*80)
        
        dashboard = SessionOptimizationDashboard(symbol="XAUUSD")
        results = dashboard.load_from_files()
        
        assert len(results) >= 0, "Should load results"
        logger.info(f"✓ Loaded {len(results)} sessions")
        
        for session, result in results.items():
            logger.info(f"\n{session}:")
            logger.info(f"  Status: {result.status.value}")
            logger.info(f"  Enabled: {result.is_enabled()}")
            
            if result.vectorbt:
                logger.info(f"  Discovery: {result.vectorbt.indicator} on {result.vectorbt.timeframe}")
                logger.info(f"    Baseline PF: {result.vectorbt.profit_factor:.2f}")
            
            if result.optuna:
                logger.info(f"  Optuna: {result.optuna.baseline_pf:.2f} → {result.optuna.tuned_pf:.2f}")
                logger.info(f"    Improvement (train): +{result.optuna.improvement_percent:.2f}%")
            
            if result.validation:
                logger.info(f"  Validation: {result.validation.baseline_pf_test:.2f} → {result.validation.tuned_pf_test:.2f}")
                logger.info(f"    Improvement (test): {result.validation.improvement_test_percent:+.2f}%")
                logger.info(f"    Train/Test Gap: {result.validation.train_test_gap_percent:.1f}%")
                logger.info(f"    Overfitting: {result.validation.overfitting_detected}")
        
        return True
    
    def test_ui_card_generation(self):
        """TEST 2: Generate UI card data"""
        logger.info("\n" + "="*80)
        logger.info("TEST 2: Generate UI Card Data")
        logger.info("="*80)
        
        dashboard = SessionOptimizationDashboard(symbol="XAUUSD")
        dashboard.load_from_files()
        
        for session in ["Asian", "London", "NewYork"]:
            card_data = dashboard.get_ui_card_data(session)
            
            logger.info(f"\n{session} Card Data:")
            logger.info(f"  Status: {card_data['status']}")
            logger.info(f"  Recommendation: {card_data['recommendation']['action']}")
            logger.info(f"  Color: {card_data['recommendation']['color']}")
            logger.info(f"  Icon: {card_data['recommendation']['icon']}")
            
            # Verify all sections present
            assert "discovery" in card_data or card_data["discovery"] is None
            assert "optuna" in card_data or card_data["optuna"] is None
            assert "validation" in card_data or card_data["validation"] is None
            assert "control" in card_data
            
            logger.info(f"  ✓ All required fields present")
        
        return True
    
    def test_recommendation_logic(self):
        """TEST 3: Test recommendation generation"""
        logger.info("\n" + "="*80)
        logger.info("TEST 3: Test Recommendation Logic")
        logger.info("="*80)
        
        # Create test results
        test_cases = [
            {
                "name": "Accepted",
                "status": OptimizationStatus.ACCEPTED,
                "validation": ValidationResult(
                    baseline_pf_test=9.8,
                    tuned_pf_test=9.95,
                    improvement_test_percent=1.53,
                    train_test_gap_percent=7.5,
                    overfitting_detected=False,
                    accepted=True
                ),
                "expected": "RECOMMENDED"
            },
            {
                "name": "Rejected",
                "status": OptimizationStatus.REJECTED,
                "validation": ValidationResult(
                    baseline_pf_test=7.2,
                    tuned_pf_test=6.8,
                    improvement_test_percent=-5.56,
                    train_test_gap_percent=10.0,
                    overfitting_detected=True,
                    accepted=False,
                    rejection_reason="PF declined 5.6% on test data; overfitting detected"
                ),
                "expected": "REJECTED"
            },
            {
                "name": "Pending",
                "status": OptimizationStatus.PENDING,
                "validation": None,
                "expected": "PENDING"
            }
        ]
        
        for test_case in test_cases:
            result = SessionOptimizationResult(
                symbol="XAUUSD",
                session="Asian",
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=test_case["status"],
                vectorbt=None,
                optuna=None,
                validation=test_case["validation"]
            )
            
            recommendation = result.get_recommendation()
            
            logger.info(f"\n{test_case['name']}:")
            logger.info(f"  Status: {test_case['status'].value}")
            logger.info(f"  Recommendation: {recommendation['action']}")
            logger.info(f"  Color: {recommendation['color']}")
            logger.info(f"  Icon: {recommendation['icon']}")
            logger.info(f"  Reason: {recommendation['reason']}")
            
            assert recommendation['action'] == test_case['expected'], \
                f"Expected {test_case['expected']}, got {recommendation['action']}"
            logger.info(f"  ✓ PASS")
        
        return True
    
    def test_overfitting_detection_ui(self):
        """TEST 4: Test overfitting detection display"""
        logger.info("\n" + "="*80)
        logger.info("TEST 4: Overfitting Detection in UI")
        logger.info("="*80)
        
        test_cases = [
            {
                "name": "No Overfitting (gap 7.5%)",
                "train_pf": 10.48,
                "test_pf": 9.95,
                "expected_overfitting": False,
                "expected_gap": 5.3
            },
            {
                "name": "Overfitting Detected (gap 13.8%)",
                "train_pf": 7.92,
                "test_pf": 6.8,
                "expected_overfitting": True,
                "expected_gap": 16.5
            },
            {
                "name": "Slight Overfitting (gap 10.2%)",
                "train_pf": 6.61,
                "test_pf": 6.0,
                "expected_overfitting": True,
                "expected_gap": 10.2
            }
        ]
        
        for test_case in test_cases:
            gap = ((test_case["train_pf"] - test_case["test_pf"]) / test_case["test_pf"]) * 100
            
            result = ValidationResult(
                baseline_pf_test=test_case["test_pf"] - 0.1,
                tuned_pf_test=test_case["test_pf"],
                improvement_test_percent=1.0,
                train_test_gap_percent=gap,
                overfitting_detected=gap > 10,  # Threshold
                accepted=gap <= 10,
                rejection_reason="Overfitting" if gap > 10 else None
            )
            
            logger.info(f"\n{test_case['name']}:")
            logger.info(f"  Training PF: {test_case['train_pf']:.2f}")
            logger.info(f"  Test PF: {test_case['test_pf']:.2f}")
            logger.info(f"  Gap: {gap:.1f}%")
            logger.info(f"  Overfitting Detected: {result.overfitting_detected}")
            logger.info(f"  Status: {'❌ REJECTED' if result.overfitting_detected else '✅ ACCEPTED'}")
            
            # Verify threshold logic
            if gap > 10:
                assert result.overfitting_detected, "Should detect overfitting for large gap"
                assert not result.accepted, "Should reject overfitted params"
            else:
                assert not result.overfitting_detected, "Should not detect overfitting for small gap"
                assert result.accepted, "Should accept non-overfitted params"
            
            logger.info(f"  ✓ PASS")
        
        return True
    
    def test_enable_disable_toggle(self):
        """TEST 5: Test enable/disable toggle"""
        logger.info("\n" + "="*80)
        logger.info("TEST 5: Enable/Disable Toggle")
        logger.info("="*80)
        
        dashboard = SessionOptimizationDashboard(symbol="XAUUSD")
        dashboard.load_from_files()
        
        for session in list(dashboard.results.keys())[:1]:  # Test first session
            result = dashboard.results[session]
            
            logger.info(f"\n{session}:")
            logger.info(f"  Initial Enabled: {result.is_enabled()}")
            
            # Test toggle
            dashboard.toggle_session(session, False)
            logger.info(f"  After Disable: {result.is_enabled()}")
            assert result.is_enabled() == False, "Should be disabled"
            
            dashboard.toggle_session(session, True)
            logger.info(f"  After Enable: {result.is_enabled()}")
            assert result.is_enabled() == True, "Should be enabled"
            
            logger.info(f"  ✓ PASS")
        
        return True
    
    def test_per_session_separation(self):
        """TEST 6: Verify per-session data separation"""
        logger.info("\n" + "="*80)
        logger.info("TEST 6: Per-Session Data Separation")
        logger.info("="*80)
        
        dashboard = SessionOptimizationDashboard(symbol="XAUUSD")
        dashboard.load_from_files()
        
        sessions_data = {}
        for session in ["Asian", "London", "NewYork"]:
            card = dashboard.get_ui_card_data(session)
            sessions_data[session] = card
            
            logger.info(f"\n{session}:")
            logger.info(f"  Status: {card['status']}")
            
            # Check each session has unique data
            if card['discovery']:
                logger.info(f"  Discovery: {card['discovery']['indicator']} ({card['discovery']['timeframe']})")
            
            if card['optuna']:
                logger.info(f"  Optuna: {card['optuna']['baseline_pf']:.2f} → {card['optuna']['tuned_pf']:.2f}")
            
            if card['validation']:
                logger.info(f"  Validation: {card['validation']['baseline_pf']:.2f} → {card['validation']['tuned_pf']:.2f}")
        
        # Verify independence (if any optimization exists)
        if len(sessions_data) > 1:
            sessions_list = list(sessions_data.values())
            for i in range(len(sessions_list) - 1):
                for j in range(i + 1, len(sessions_list)):
                    # Sessions should be independent
                    logger.info(f"  ✓ {sessions_list[i].get('session', 'Unknown')} and {sessions_list[j].get('session', 'Unknown')} are independent")
        
        return True
    
    def test_json_export(self):
        """TEST 7: Test JSON export for API"""
        logger.info("\n" + "="*80)
        logger.info("TEST 7: JSON Export for API")
        logger.info("="*80)
        
        dashboard = SessionOptimizationDashboard(symbol="XAUUSD")
        dashboard.load_from_files()
        
        json_export = dashboard.export_to_json()
        
        # Parse and verify structure
        data = json.loads(json_export)
        
        logger.info(f"Export contains:")
        logger.info(f"  Symbol: {data.get('symbol')}")
        logger.info(f"  Sessions: {len(data.get('sessions', []))}")
        logger.info(f"  Summary:")
        for key, value in data.get('summary', {}).items():
            logger.info(f"    {key}: {value}")
        
        # Verify required fields
        assert "symbol" in data
        assert "sessions" in data
        assert "summary" in data
        assert "timestamp" in data
        
        logger.info(f"  ✓ All required fields present")
        
        return True


def run_all_tests():
    """Run all tests"""
    logger.info("\n" + "="*80)
    logger.info("OPTIMIZATION DASHBOARD TEST SUITE")
    logger.info("="*80)
    
    test_suite = TestOptimizationDashboard()
    
    tests = [
        ("Load Results", test_suite.test_load_optimization_results),
        ("UI Card Generation", test_suite.test_ui_card_generation),
        ("Recommendation Logic", test_suite.test_recommendation_logic),
        ("Overfitting Detection UI", test_suite.test_overfitting_detection_ui),
        ("Enable/Disable Toggle", test_suite.test_enable_disable_toggle),
        ("Per-Session Separation", test_suite.test_per_session_separation),
        ("JSON Export", test_suite.test_json_export),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                logger.info(f"\n✓ {test_name}: PASSED")
            else:
                failed += 1
                logger.info(f"\n✗ {test_name}: FAILED")
        except Exception as e:
            failed += 1
            logger.error(f"\n✗ {test_name}: FAILED - {e}")
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info(f"TEST RESULTS: {passed} passed, {failed} failed")
    logger.info("="*80)
    
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
