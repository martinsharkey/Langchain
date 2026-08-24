import React, { useState, useEffect } from 'react';
import io from 'socket.io-client';
import './App.css';

const API_URL = 'http://localhost:5000/api';
const SOCKET = io('http://localhost:5000');

export default function App() {
  const [availableSymbols, setAvailableSymbols] = useState([]);
  const [onboardedSymbols, setOnboardedSymbols] = useState([]);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [symbolStatus, setSymbolStatus] = useState({});
  const [onboardingProgress, setOnboardingProgress] = useState({});
  const [stats, setStats] = useState({ total_onboarded: 0, total_sessions: 0, total_configs_tested: 0 });

  // Fetch available symbols
  useEffect(() => {
    const fetchSymbols = async () => {
      try {
        const res = await fetch(`${API_URL}/symbols/available`);
        const data = await res.json();
        setAvailableSymbols(data.symbols);
      } catch (err) {
        console.error('Error fetching symbols:', err);
      }
    };
    fetchSymbols();
  }, []);

  // Fetch onboarded symbols
  useEffect(() => {
    const fetchOnboarded = async () => {
      try {
        const res = await fetch(`${API_URL}/symbols/onboarded`);
        const data = await res.json();
        setOnboardedSymbols(data.symbols);
        
        // Fetch status for each
        for (const symbol of data.symbols) {
          const statusRes = await fetch(`${API_URL}/symbol/${symbol}/status`);
          const statusData = await statusRes.json();
          setSymbolStatus(prev => ({ ...prev, [symbol]: statusData }));
        }
      } catch (err) {
        console.error('Error fetching onboarded:', err);
      }
    };
    
    fetchOnboarded();
    const interval = setInterval(fetchOnboarded, 5000);
    return () => clearInterval(interval);
  }, []);

  // Fetch stats
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_URL}/stats`);
        const data = await res.json();
        setStats(data);
      } catch (err) {
        console.error('Error fetching stats:', err);
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  // Listen for onboarding updates
  useEffect(() => {
    SOCKET.on('onboarding_update', (data) => {
      setOnboardingProgress(prev => ({
        ...prev,
        [data.symbol || 'current']: data
      }));
    });

    return () => SOCKET.off('onboarding_update');
  }, []);

  const handleOnboard = async (symbol) => {
    try {
      setOnboardingProgress(prev => ({
        ...prev,
        [symbol]: { status: 'starting', progress: 0, message: 'Starting...' }
      }));
      
      const res = await fetch(`${API_URL}/symbol/${symbol}/onboard`, { method: 'POST' });
      const data = await res.json();
      
      if (data.error) {
        alert(`Error: ${data.error}`);
      }
    } catch (err) {
      console.error('Error onboarding:', err);
      alert('Failed to start onboarding');
    }
  };

  const handleRemove = async (symbol) => {
    if (!window.confirm(`Remove ${symbol}?`)) return;
    
    try {
      await fetch(`${API_URL}/symbol/${symbol}/remove`, { method: 'POST' });
      setOnboardedSymbols(prev => prev.filter(s => s !== symbol));
      setSymbolStatus(prev => {
        const newStatus = { ...prev };
        delete newStatus[symbol];
        return newStatus;
      });
    } catch (err) {
      console.error('Error removing:', err);
      alert('Failed to remove symbol');
    }
  };

  const handleRefresh = async (symbol) => {
    await handleOnboard(symbol);
  };

  const handleUseInBot = async (symbol) => {
    try {
      const res = await fetch(`${API_URL}/symbol/${symbol}/use-in-bot`, { method: 'POST' });
      const data = await res.json();
      alert(`Added ${symbol} to live bot`);
    } catch (err) {
      console.error('Error:', err);
      alert('Failed to add to bot');
    }
  };

  const handleGenerateEA = async (symbol) => {
    try {
      const res = await fetch(`${API_URL}/symbol/${symbol}/download-ea`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `GoldShark_${symbol}_vectorbt.mq5`;
        a.click();
      }
    } catch (err) {
      console.error('Error downloading EA:', err);
      alert('Failed to download EA');
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Symbol Onboarding Manager</h1>
        <div className="stats">
          <div className="stat-item">
            <span className="stat-label">Onboarded:</span>
            <span className="stat-value">{stats.total_onboarded}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Sessions:</span>
            <span className="stat-value">{stats.total_sessions}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Configs:</span>
            <span className="stat-value">{stats.total_configs_tested.toLocaleString()}</span>
          </div>
        </div>
      </header>

      <main className="main">
        <section className="available-symbols">
          <h2>Available Symbols</h2>
          <div className="symbol-list">
            {availableSymbols.map(symbol => (
              <SymbolCard
                key={symbol}
                symbol={symbol}
                isOnboarded={onboardedSymbols.includes(symbol)}
                status={symbolStatus[symbol]}
                progress={onboardingProgress[symbol]}
                onOnboard={() => handleOnboard(symbol)}
                onRemove={() => handleRemove(symbol)}
                onRefresh={() => handleRefresh(symbol)}
                onUseInBot={() => handleUseInBot(symbol)}
                onGenerateEA={() => handleGenerateEA(symbol)}
              />
            ))}
          </div>
        </section>

        <section className="onboarded-symbols">
          <h2>Onboarded Symbols</h2>
          <div className="symbol-grid">
            {onboardedSymbols.map(symbol => (
              <OnboardedSymbolCard
                key={symbol}
                symbol={symbol}
                status={symbolStatus[symbol]}
                onRemove={() => handleRemove(symbol)}
                onRefresh={() => handleRefresh(symbol)}
                onUseInBot={() => handleUseInBot(symbol)}
                onGenerateEA={() => handleGenerateEA(symbol)}
              />
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function SymbolCard({ symbol, isOnboarded, status, progress, onOnboard, onRemove, onRefresh, onUseInBot, onGenerateEA }) {
  return (
    <div className={`symbol-card ${isOnboarded ? 'onboarded' : 'available'}`}>
      <h3>{symbol}</h3>
      
      {progress && progress.status === 'running' && (
        <div className="progress-container">
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progress.progress}%` }}></div>
          </div>
          <p className="progress-message">{progress.message}</p>
          <p className="progress-percent">{progress.progress}%</p>
        </div>
      )}

      {status && status.result && (
        <div className="results">
          <h4>Top 3 Strategies:</h4>
          {status.result.top_strategies.map((strat, i) => (
            <div key={i} className="strategy">
              <div className="strategy-header">
                #{i + 1} {strat.session}
              </div>
              <div className="strategy-metrics">
                <span>PF: {strat.pf}</span>
                <span>WR: {(strat.wr * 100).toFixed(1)}%</span>
                <span>Sharpe: {strat.sharpe}</span>
              </div>
              <div className="strategy-indicators">
                {strat.primary_ind} + {strat.secondary_ind}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="actions">
        {!isOnboarded ? (
          <button className="btn btn-primary" onClick={onOnboard} disabled={progress?.status === 'running'}>
            {progress?.status === 'running' ? 'Onboarding...' : 'Onboard'}
          </button>
        ) : (
          <>
            <button className="btn btn-secondary" onClick={onRefresh}>Refresh</button>
            <button className="btn btn-success" onClick={onUseInBot}>Use in Bot</button>
            <button className="btn btn-info" onClick={onGenerateEA}>Generate EA</button>
            <button className="btn btn-danger" onClick={onRemove}>Remove</button>
          </>
        )}
      </div>
    </div>
  );
}

function OnboardedSymbolCard({ symbol, status, onRemove, onRefresh, onUseInBot, onGenerateEA }) {
  return (
    <div className="symbol-card-detailed">
      <div className="card-header">
        <h3>{symbol}</h3>
        <span className="status-badge">Onboarded</span>
      </div>

      {status && status.result && (
        <div className="card-content">
          <div className="metrics-grid">
            <div className="metric">
              <span className="metric-label">Strategies Validated</span>
              <span className="metric-value">{status.result.validated_strategies}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Last Updated</span>
              <span className="metric-value">{new Date(status.result.timestamp).toLocaleDateString()}</span>
            </div>
          </div>

          <div className="top-strategies">
            <h4>Best Strategies:</h4>
            {status.result.top_strategies.map((strat, i) => (
              <div key={i} className="strategy-row">
                <div className="strategy-rank">#{i + 1}</div>
                <div className="strategy-info">
                  <div className="strategy-session">{strat.session}</div>
                  <div className="strategy-indicators">{strat.primary_ind} + {strat.secondary_ind}</div>
                </div>
                <div className="strategy-metrics">
                  <span className="metric-pf">PF {strat.pf}</span>
                  <span className="metric-wr">{(strat.wr * 100).toFixed(1)}%</span>
                  <span className="metric-sharpe">Sharpe {strat.sharpe}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card-actions">
        <button className="btn btn-secondary" onClick={onRefresh}>Refresh</button>
        <button className="btn btn-success" onClick={onUseInBot}>Use in Bot</button>
        <button className="btn btn-info" onClick={onGenerateEA}>Download EA</button>
        <button className="btn btn-danger" onClick={onRemove}>Remove</button>
      </div>
    </div>
  );
}
