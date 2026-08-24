"""
Session Optimization Results Dashboard Component

Displays per-session Vectorbt discovery, Optuna tuning results, and validation
recommendations with enable/disable controls.

Features:
- Per-session optimization results (Vectorbt → Optuna → Validation)
- Enable/Disable toggle per session
- Clear recommendation (Accept/Reject with reasoning)
- Override capability
- Visual indicators for status
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import json
from datetime import datetime, timezone
from pathlib import Path


class OptimizationStatus(Enum):
    """Optimization status for a session"""
    PENDING = "pending"           # Not yet optimized
    OPTIMIZING = "optimizing"     # Currently running
    COMPLETED = "completed"       # Optimization complete
    ACCEPTED = "accepted"         # Tuned params validated and deployed
    REJECTED = "rejected"         # Validation failed, baseline used
    ERROR = "error"               # Optimization failed


@dataclass
class VectorbtResult:
    """Vectorbt discovery result"""
    indicator: str
    timeframe: str
    profit_factor: float
    win_rate: float
    trades: int
    baseline_params: Dict


@dataclass
class OptunaResult:
    """Optuna tuning result"""
    baseline_pf: float
    tuned_pf: float
    improvement_percent: float
    baseline_params: Dict
    tuned_params: Dict
    n_trials: int


@dataclass
class ValidationResult:
    """Walk-forward validation result"""
    baseline_pf_test: float
    tuned_pf_test: float
    improvement_test_percent: float
    train_test_gap_percent: float
    overfitting_detected: bool
    accepted: bool
    rejection_reason: Optional[str] = None


@dataclass
class SessionOptimizationResult:
    """Complete optimization result for one session"""
    symbol: str
    session: str                    # Asian, London, NewYork
    timestamp: str                  # ISO8601
    status: OptimizationStatus
    
    # Optimization phases
    vectorbt: Optional[VectorbtResult]
    optuna: Optional[OptunaResult]
    validation: Optional[ValidationResult]
    
    # UI State
    enabled: bool = True            # Enable/disable toggle
    override_enabled: Optional[bool] = None  # User override
    
    def get_recommendation(self) -> Dict[str, any]:
        """Get UI recommendation for this session"""
        if self.status == OptimizationStatus.REJECTED:
            return {
                "action": "REJECTED",
                "recommendation": "Tuned parameters overfitted on training data",
                "color": "red",
                "icon": "❌",
                "reason": self.validation.rejection_reason if self.validation else "Unknown"
            }
        elif self.status == OptimizationStatus.ACCEPTED:
            return {
                "action": "RECOMMENDED",
                "recommendation": f"Deploy tuned params (+{self.validation.improvement_test_percent:.2f}%)",
                "color": "green",
                "icon": "✅",
                "reason": "Validation passed on unseen test data"
            }
        elif self.status == OptimizationStatus.OPTIMIZING:
            return {
                "action": "RUNNING",
                "recommendation": "Optimization in progress...",
                "color": "blue",
                "icon": "🔄",
                "reason": "Please wait"
            }
        elif self.status == OptimizationStatus.PENDING:
            return {
                "action": "PENDING",
                "recommendation": "Not yet optimized",
                "color": "gray",
                "icon": "⏳",
                "reason": "Run optimization to generate recommendation"
            }
        else:
            return {
                "action": "ERROR",
                "recommendation": "Optimization failed",
                "color": "orange",
                "icon": "⚠️",
                "reason": "Check logs for details"
            }
    
    def is_enabled(self) -> bool:
        """Check if this session is enabled for live trading"""
        if self.override_enabled is not None:
            return self.override_enabled
        return self.enabled


class SessionOptimizationDashboard:
    """Dashboard for displaying and managing session optimizations"""
    
    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.sessions = ["Asian", "London", "NewYork"]
        self.results: Dict[str, SessionOptimizationResult] = {}
        
    def load_from_files(self) -> Dict[str, SessionOptimizationResult]:
        """Load optimization results from files"""
        
        # Load discovery results
        discovery_file = Path("data/qmmp") / self.symbol / f"phase1_discovery_{self.symbol}.json"
        discovery_data = {}
        if discovery_file.exists():
            with open(discovery_file) as f:
                discovery_data = json.load(f).get("best_by_session", {})
        
        # Load Optuna results
        optuna_file = Path("data/qmmp") / self.symbol / f"phase2_optuna_{self.symbol}.json"
        optuna_data = {}
        if optuna_file.exists():
            with open(optuna_file) as f:
                optuna_data = json.load(f).get("results", {})
        
        # Load validation results
        validation_file = Path("data/qmmp") / self.symbol / f"phase3_validation_{self.symbol}.json"
        validation_data = {}
        if validation_file.exists():
            with open(validation_file) as f:
                validation_data = json.load(f).get("results", {})
        
        # Build results for each session
        for session in self.sessions:
            vbt_data = discovery_data.get(session, {})
            opt_data = optuna_data.get(session, {})
            val_data = validation_data.get(session, {})
            
            # Determine status
            if val_data:
                status = (
                    OptimizationStatus.ACCEPTED if val_data.get("accepted") 
                    else OptimizationStatus.REJECTED
                )
            elif opt_data:
                status = OptimizationStatus.COMPLETED
            elif vbt_data:
                status = OptimizationStatus.COMPLETED
            else:
                status = OptimizationStatus.PENDING
            
            # Build components
            vectorbt_result = None
            if vbt_data:
                vectorbt_result = VectorbtResult(
                    indicator=vbt_data.get("indicator"),
                    timeframe=vbt_data.get("timeframe", "H4"),
                    profit_factor=vbt_data.get("profit_factor", 0),
                    win_rate=vbt_data.get("win_rate", 0),
                    trades=vbt_data.get("trades", 0),
                    baseline_params=vbt_data.get("baseline_params", {})
                )
            
            optuna_result = None
            if opt_data:
                optuna_result = OptunaResult(
                    baseline_pf=opt_data.get("baseline_pf_train", 0),
                    tuned_pf=opt_data.get("tuned_pf_train", 0),
                    improvement_percent=opt_data.get("improvement_train", 0) * 100,
                    baseline_params=opt_data.get("baseline_params", {}),
                    tuned_params=opt_data.get("tuned_params", {}),
                    n_trials=opt_data.get("n_trials", 100)
                )
            
            validation_result = None
            if val_data:
                validation_result = ValidationResult(
                    baseline_pf_test=val_data.get("baseline_pf_test", 0),
                    tuned_pf_test=val_data.get("tuned_pf_test", 0),
                    improvement_test_percent=val_data.get("improvement_test", 0) * 100,
                    train_test_gap_percent=val_data.get("train_vs_test_gap", 0) * 100,
                    overfitting_detected=val_data.get("rejection_reason") is not None,
                    accepted=val_data.get("accepted", False),
                    rejection_reason=val_data.get("rejection_reason")
                )
            
            result = SessionOptimizationResult(
                symbol=self.symbol,
                session=session,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=status,
                vectorbt=vectorbt_result,
                optuna=optuna_result,
                validation=validation_result,
            )
            
            self.results[session] = result
        
        return self.results
    
    def get_ui_card_data(self, session: str) -> Dict:
        """Get UI card data for one session"""
        
        if session not in self.results:
            return {"error": f"Session {session} not found"}
        
        result = self.results[session]
        recommendation = result.get_recommendation()
        
        return {
            "session": session,
            "symbol": self.symbol,
            
            # Status
            "status": result.status.value,
            "recommendation": recommendation,
            
            # Vectorbt Discovery
            "discovery": {
                "indicator": result.vectorbt.indicator if result.vectorbt else None,
                "timeframe": result.vectorbt.timeframe if result.vectorbt else None,
                "baseline_pf": result.vectorbt.profit_factor if result.vectorbt else None,
                "win_rate": result.vectorbt.win_rate if result.vectorbt else None,
                "trades": result.vectorbt.trades if result.vectorbt else None,
            } if result.vectorbt else None,
            
            # Optuna Tuning (Training)
            "optuna": {
                "baseline_pf": result.optuna.baseline_pf if result.optuna else None,
                "tuned_pf": result.optuna.tuned_pf if result.optuna else None,
                "improvement_percent": result.optuna.improvement_percent if result.optuna else None,
                "n_trials": result.optuna.n_trials if result.optuna else None,
                "baseline_params": result.optuna.baseline_params if result.optuna else None,
                "tuned_params": result.optuna.tuned_params if result.optuna else None,
            } if result.optuna else None,
            
            # Validation (Test Data)
            "validation": {
                "baseline_pf": result.validation.baseline_pf_test if result.validation else None,
                "tuned_pf": result.validation.tuned_pf_test if result.validation else None,
                "improvement_percent": result.validation.improvement_test_percent if result.validation else None,
                "train_test_gap": result.validation.train_test_gap_percent if result.validation else None,
                "overfitting": result.validation.overfitting_detected if result.validation else None,
            } if result.validation else None,
            
            # Enable/Disable Control
            "control": {
                "enabled": result.is_enabled(),
                "override": result.override_enabled,
                "can_override": result.status in [
                    OptimizationStatus.ACCEPTED,
                    OptimizationStatus.REJECTED
                ]
            }
        }
    
    def get_all_cards(self) -> List[Dict]:
        """Get UI data for all sessions"""
        return [self.get_ui_card_data(session) for session in self.sessions]
    
    def toggle_session(self, session: str, enabled: bool):
        """Toggle session enabled/disabled"""
        if session in self.results:
            self.results[session].override_enabled = enabled
            return True
        return False
    
    def export_to_json(self) -> str:
        """Export all results as JSON for API response"""
        cards = self.get_all_cards()
        return json.dumps({
            "symbol": self.symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sessions": cards,
            "summary": {
                "total_sessions": len(self.sessions),
                "accepted": sum(1 for r in self.results.values() if r.status == OptimizationStatus.ACCEPTED),
                "rejected": sum(1 for r in self.results.values() if r.status == OptimizationStatus.REJECTED),
                "pending": sum(1 for r in self.results.values() if r.status == OptimizationStatus.PENDING),
            }
        }, indent=2)


# Example HTML/React component structure
OPTIMIZATION_CARD_TEMPLATE = """
<div class="session-optimization-card">
  <!-- Header with Status -->
  <div class="card-header" style="background-color: {recommendation.color}">
    <span class="status-icon">{recommendation.icon}</span>
    <span class="session-name">{session}</span>
    <span class="recommendation-text">{recommendation.action}</span>
  </div>
  
  <!-- Discovery Results -->
  <div class="section">
    <h3>Vectorbt Discovery</h3>
    <div class="metric">
      <label>Indicator:</label>
      <value>{discovery.indicator}</value>
    </div>
    <div class="metric">
      <label>Timeframe:</label>
      <value>{discovery.timeframe}</value>
    </div>
    <div class="metric">
      <label>Baseline PF:</label>
      <value>{discovery.baseline_pf:.2f}</value>
    </div>
    <div class="metric">
      <label>Trades:</label>
      <value>{discovery.trades}</value>
    </div>
  </div>
  
  <!-- Optuna Results -->
  <div class="section" style="background-color: #f0f0f0">
    <h3>Optuna Tuning (Training Data)</h3>
    <div class="metric">
      <label>Baseline PF:</label>
      <value>{optuna.baseline_pf:.2f}</value>
    </div>
    <div class="metric">
      <label>Tuned PF:</label>
      <value style="color: blue">{optuna.tuned_pf:.2f}</value>
    </div>
    <div class="metric">
      <label>Improvement:</label>
      <value style="color: blue">+{optuna.improvement_percent:.2f}%</value>
    </div>
    <div class="metric">
      <label>Trials:</label>
      <value>{optuna.n_trials}</value>
    </div>
  </div>
  
  <!-- Validation Results -->
  <div class="section">
    <h3>Validation (Test Data - Out of Sample)</h3>
    <div class="metric">
      <label>Baseline PF:</label>
      <value>{validation.baseline_pf:.2f}</value>
    </div>
    <div class="metric">
      <label>Tuned PF:</label>
      <value style="color: {validation_color}">{validation.tuned_pf:.2f}</value>
    </div>
    <div class="metric">
      <label>Improvement:</label>
      <value style="color: {validation_color}">{validation.improvement_percent:+.2f}%</value>
    </div>
    <div class="metric">
      <label>Train/Test Gap:</label>
      <value style="color: {gap_color}">{validation.train_test_gap:.1f}%</value>
    </div>
    <div class="metric" style="background: {overfitting_bg}; padding: 8px">
      <label>Overfitting:</label>
      <value>{overfitting_status}</value>
    </div>
  </div>
  
  <!-- Recommendation -->
  <div class="recommendation-box" style="background-color: {recommendation.color}20; border-left: 4px solid {recommendation.color}">
    <strong>{recommendation.recommendation}</strong>
    <p>{recommendation.reason}</p>
  </div>
  
  <!-- Enable/Disable Toggle -->
  <div class="control-section">
    <label>Enable for Live Trading:</label>
    <toggle 
      value="{control.enabled}"
      on-change="toggle_session('{session}')"
      disabled="{not control.can_override}"
    />
    <small>{control_status}</small>
  </div>
  
  <!-- Deployed Status -->
  <div class="deployment-status">
    {deployment_status_icon} Deployed: {deployed_file}
  </div>
</div>
"""
