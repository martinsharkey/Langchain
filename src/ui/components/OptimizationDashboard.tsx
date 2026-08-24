/**
 * React Component: Session Optimization Dashboard
 * 
 * Displays per-session optimization results with:
 * - Vectorbt discovery
 * - Optuna tuning
 * - Validation results
 * - Enable/disable toggle
 * - Color-coded recommendations
 */

import React, { useState, useEffect } from 'react';
import './optimization-dashboard.css';

const OptimizationDashboard = ({ symbol = 'XAUUSD' }) => {
  const [sessions, setSessions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchOptimizationResults();
  }, [symbol]);

  const fetchOptimizationResults = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/v2/optimization/results/${symbol}`);
      if (!response.ok) throw new Error('Failed to fetch optimization results');
      
      const data = await response.json();
      setSessions(data.sessions || []);
      setSummary(data.summary);
      setError(null);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching optimization results:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleSession = async (session, enabled) => {
    try {
      const response = await fetch(
        `/api/v2/optimization/control/${symbol}/${session}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: !enabled })
        }
      );
      
      if (!response.ok) throw new Error('Failed to toggle session');
      
      // Refresh results
      await fetchOptimizationResults();
    } catch (err) {
      setError(err.message);
      console.error('Error toggling session:', err);
    }
  };

  if (loading) return <div className="optimization-dashboard loading">Loading...</div>;
  if (error) return <div className="optimization-dashboard error">Error: {error}</div>;

  return (
    <div className="optimization-dashboard">
      <div className="dashboard-header">
        <h2>Session Optimization: {symbol}</h2>
        {summary && (
          <div className="summary-stats">
            <span className="stat">
              <span className="stat-label">Total:</span>
              <span className="stat-value">{summary.total_sessions}</span>
            </span>
            <span className="stat stat-accepted">
              <span className="stat-label">Accepted:</span>
              <span className="stat-value">{summary.accepted}</span>
            </span>
            <span className="stat stat-rejected">
              <span className="stat-label">Rejected:</span>
              <span className="stat-value">{summary.rejected}</span>
            </span>
            <span className="stat stat-enabled">
              <span className="stat-label">Enabled:</span>
              <span className="stat-value">{summary.enabled}</span>
            </span>
          </div>
        )}
      </div>

      <div className="sessions-grid">
        {sessions.map((session) => (
          <SessionOptimizationCard
            key={session.session}
            session={session}
            symbol={symbol}
            onToggle={handleToggleSession}
          />
        ))}
      </div>
    </div>
  );
};

const SessionOptimizationCard = ({ session, symbol, onToggle }) => {
  const rec = session.recommendation;
  const discovery = session.discovery;
  const optuna = session.optuna;
  const validation = session.validation;
  const control = session.control;

  const getGapColor = (gap) => {
    if (gap === null || gap === undefined) return '#ccc';
    return gap > 10 ? '#ff6b6b' : '#51cf66'; // Red if overfitting, green otherwise
  };

  const getOverfittingText = (gap) => {
    if (gap === null || gap === undefined) return 'N/A';
    return gap > 10 ? '⚠️ Overfitting Detected' : '✓ Good Generalization';
  };

  return (
    <div className={`session-card status-${rec.action.toLowerCase()}`}>
      {/* Header */}
      <div className="card-header" style={{ backgroundColor: rec.color }}>
        <span className="header-icon">{rec.icon}</span>
        <span className="header-session">{session.session}</span>
        <span className="header-action">{rec.action}</span>
      </div>

      {/* Content */}
      <div className="card-content">
        {/* Discovery Section */}
        {discovery && (
          <div className="section">
            <h4>Vectorbt Discovery</h4>
            <div className="metric-row">
              <span className="metric-label">Indicator:</span>
              <span className="metric-value">{discovery.indicator}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Timeframe:</span>
              <span className="metric-value">{discovery.timeframe}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Baseline PF:</span>
              <span className="metric-value metric-pf">{discovery.baseline_pf?.toFixed(2)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Trades:</span>
              <span className="metric-value">{discovery.trades}</span>
            </div>
          </div>
        )}

        {/* Optuna Section */}
        {optuna && (
          <div className="section section-optuna">
            <h4>Optuna Tuning (Training Data)</h4>
            <div className="metric-row">
              <span className="metric-label">Baseline PF:</span>
              <span className="metric-value metric-pf">{optuna.baseline_pf?.toFixed(2)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Tuned PF:</span>
              <span className="metric-value metric-pf metric-tuned">{optuna.tuned_pf?.toFixed(2)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Improvement:</span>
              <span className="metric-value metric-improvement">
                +{optuna.improvement_percent?.toFixed(2)}%
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Trials:</span>
              <span className="metric-value">{optuna.n_trials}</span>
            </div>
          </div>
        )}

        {/* Validation Section */}
        {validation && (
          <div className="section section-validation">
            <h4>Validation (Test Data - Out of Sample) ⭐</h4>
            <div className="metric-row">
              <span className="metric-label">Baseline PF:</span>
              <span className="metric-value metric-pf">{validation.baseline_pf?.toFixed(2)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Tuned PF:</span>
              <span className="metric-value metric-pf">{validation.tuned_pf?.toFixed(2)}</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Improvement:</span>
              <span className="metric-value metric-improvement">
                {validation.improvement_percent > 0 ? '+' : ''}{validation.improvement_percent?.toFixed(2)}%
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Train/Test Gap:</span>
              <span 
                className="metric-value"
                style={{ color: getGapColor(validation.train_test_gap) }}
              >
                {validation.train_test_gap?.toFixed(1)}%
              </span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Overfitting:</span>
              <span className="metric-value">
                {getOverfittingText(validation.train_test_gap)}
              </span>
            </div>
          </div>
        )}

        {/* Recommendation Box */}
        <div className="recommendation-box" style={{ borderLeftColor: rec.color }}>
          <strong>{rec.recommendation}</strong>
          <p>{rec.reason}</p>
        </div>

        {/* Control Section */}
        {control && (
          <div className="control-section">
            <label>Enable for Live Trading:</label>
            <button
              className={`toggle-btn ${control.enabled ? 'enabled' : 'disabled'}`}
              onClick={() => onToggle(session.session, control.enabled)}
              disabled={!control.can_override}
              title={control.can_override ? 'Click to toggle' : 'Cannot toggle unfinalized session'}
            >
              <span className="toggle-icon">{control.enabled ? '☑' : '☐'}</span>
              <span className="toggle-label">{control.enabled ? 'ENABLED' : 'DISABLED'}</span>
            </button>
            {!control.can_override && (
              <small className="control-note">Cannot toggle - optimization not finalized</small>
            )}
          </div>
        )}

        {/* Deployment Status */}
        {session.status === 'accepted' || session.status === 'rejected' && (
          <div className="deployment-status">
            <span className="status-icon">✓</span>
            <span className="status-text">Deployed</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default OptimizationDashboard;
