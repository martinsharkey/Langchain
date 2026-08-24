"""
Tests for Dashboard API v2.

Tests:
  1. Strategy list endpoint
  2. Individual strategy detail
  3. Backtest results endpoint
  4. Vectorbt discovery endpoint
  5. Summary statistics
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from src.dashboard.api_v2 import DashboardAPIv2


class TestDashboardAPIv2:
    """Test dashboard API endpoints."""
    
    @pytest.fixture
    def temp_config(self):
        """Create temporary config directory with test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create edge_weights.json
            edge_weights = {
                "edge_weights": {
                    "XAUUSD": {"OsMA_Confluence": 1.45}
                },
                "regime_edge": {
                    "XAUUSD": {
                        "OsMA_Confluence": {
                            "trending": 1.30,
                            "volatile": 1.15,
                            "ranging": 0.90,
                            "quiet": 0.85
                        }
                    }
                },
                "focused_edge": {
                    "XAUUSD": [["OsMA_Confluence", ["trending", "volatile"]]]
                },
                "meta": {
                    "swept_at": "2026-08-24T10:00:00Z",
                    "min_pf": 1.15,
                    "timeframe": "M15",
                    "symbols": {
                        "XAUUSD": {"validated": True, "pockets": 1}
                    }
                }
            }
            
            edge_path = os.path.join(tmpdir, "edge_weights.json")
            with open(edge_path, "w") as f:
                json.dump(edge_weights, f)
            
            # Create strategy_config.json
            strategy_config = {
                "version": "1.0",
                "metadata": {
                    "description": "Test config",
                    "swept_at": "2026-08-24T10:00:00Z"
                },
                "strategies": {
                    "XAUUSD": [
                        {
                            "rank": 1,
                            "strategy": "OsMA_Confluence",
                            "enabled": True,
                            "description": "Primary strategy",
                            "parameters": {
                                "osma_fast": 12,
                                "osma_slow": 26,
                                "osma_signal": 9
                            },
                            "performance": {
                                "vectorbt_pf": 1.45,
                                "vectorbt_wr": 0.52,
                                "vectorbt_sharpe": 0.82,
                                "last_validated": "2026-08-24T10:00:00Z",
                                "validation_bars": 12000,
                                "trades_tested": 156
                            },
                            "optuna_study": None,
                            "notes": "Test strategy"
                        }
                    ],
                    "BTCUSD": [
                        {
                            "rank": 1,
                            "strategy": "Bollinger_OsMA",
                            "enabled": True,
                            "description": "Primary strategy",
                            "parameters": {
                                "max_extension_atr": 2.0,
                                "ATR_Multiplier": 1.889
                            },
                            "performance": {
                                "vectorbt_pf": 1.18,
                                "vectorbt_wr": 0.59,
                                "vectorbt_sharpe": 0.71,
                                "last_validated": "2026-08-24T09:00:00Z",
                                "validation_bars": 12000,
                                "trades_tested": 213
                            },
                            "optuna_study": "btcusd_bollinger_osma_v1",
                            "notes": "Test strategy"
                        }
                    ]
                },
                "defaults": {
                    "fallback_on_hold": True
                }
            }
            
            config_path = os.path.join(tmpdir, "strategy_config.json")
            with open(config_path, "w") as f:
                json.dump(strategy_config, f)
            
            yield tmpdir
    
    def test_list_strategies(self, temp_config):
        """Test listing all strategies."""
        api = DashboardAPIv2(":memory:", temp_config)
        
        strategies = api.list_strategies()
        
        assert len(strategies) >= 1
        assert any(s.name == "OsMA_Confluence" for s in strategies)
        assert any(s.name == "Bollinger_OsMA" for s in strategies)
    
    def test_filter_by_symbol(self, temp_config):
        """Test filtering strategies by symbol."""
        api = DashboardAPIv2(":memory:", temp_config)
        
        strategies = api.list_strategies("XAUUSD")
        
        assert len(strategies) >= 1
        assert all(s.symbol == "XAUUSD" for s in strategies)
    
    def test_strategy_has_backtest_metrics(self, temp_config):
        """Test that strategies have backtest metrics."""
        api = DashboardAPIv2(":memory:", temp_config)
        
        strategies = api.list_strategies()
        xauusd_strat = next(s for s in strategies if s.name == "OsMA_Confluence")
        
        assert xauusd_strat.vectorbt_pf == 1.45
        assert xauusd_strat.backtest is not None
        assert xauusd_strat.backtest.metrics.profit_factor == 1.45
        assert xauusd_strat.backtest.metrics.win_rate == 0.52
    
    def test_strategy_regime_edges(self, temp_config):
        """Test regime edge extraction."""
        api = DashboardAPIv2(":memory:", temp_config)
        
        strategies = api.list_strategies("XAUUSD")
        strat = next(s for s in strategies if s.name == "OsMA_Confluence")
        
        regime_edges = strat.regime_edges
        assert len(regime_edges) >= 1
        
        # Check specific regimes
        regimes_dict = {e.regime: e.multiplier for e in regime_edges}
        assert regimes_dict.get("trending") == 1.30
        assert regimes_dict.get("volatile") == 1.15
    
    def test_vectorbt_discovery(self, temp_config):
        """Test vectorbt discovery endpoint."""
        api = DashboardAPIv2(":memory:", temp_config)
        
        discovery = api.get_vectorbt_discovery()
        
        assert discovery["swept_at"] == "2026-08-24T10:00:00Z"
        assert discovery["min_pf_threshold"] == 1.15
        assert discovery["timeframe"] == "M15"
        assert "XAUUSD" in discovery["symbols"]
        assert discovery["symbols"]["XAUUSD"]["validated"] is True
    
    def test_summary_stats(self, temp_config):
        """Test dashboard summary statistics."""
        api = DashboardAPIv2(":memory:", temp_config)
        
        summary = api.get_summary_stats()
        
        assert summary["total_strategies"] >= 1
        assert summary["validated_strategies"] >= 1
        assert "best_strategy" in summary
        assert summary["best_strategy"]["name"] is not None
    
    def test_backtest_results(self, temp_config):
        """Test backtest results endpoint."""
        api = DashboardAPIv2(":memory:", temp_config)
        
        results = api.get_backtest_results()
        
        assert len(results) >= 1
        assert "symbol" in results[0]
        assert "strategy" in results[0]
        assert "profit_factor" in results[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
