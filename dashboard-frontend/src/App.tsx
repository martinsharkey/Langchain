import { Routes, Route, Link, useLocation } from 'react-router-dom'
import StrategyDashboard from './pages/StrategyDashboard'
import BacktestResults from './pages/BacktestResults'
import OptimizationDashboard from './pages/OptimizationDashboard'
import LiveTrading from './pages/LiveTrading'
import VectorbtDiscovery from './pages/VectorbtDiscovery'
import SymbolOnboarding from './pages/SymbolOnboarding'
import Header from './components/Header'
import './App.css'

function App() {
  const location = useLocation()

  const tabs = [
    { name: 'Strategies', path: '/', id: 'strategies' },
    { name: 'Backtest', path: '/backtest', id: 'backtest' },
    { name: 'Optimization', path: '/optimization', id: 'optimization' },
    { name: 'Live Trading', path: '/live', id: 'live' },
    { name: 'Discovery', path: '/discovery', id: 'discovery' },
    { name: 'Symbols', path: '/symbols', id: 'symbols' },
  ]

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Header />

      {/* Tab Navigation */}
      <nav className="border-b border-slate-800 bg-slate-900/50 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex space-x-8 overflow-x-auto">
            {tabs.map((tab) => (
              <Link
                key={tab.id}
                to={tab.path}
                className={`px-1 py-4 border-b-2 font-medium text-sm transition-colors whitespace-nowrap ${
                  location.pathname === tab.path
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-slate-400 hover:text-slate-300'
                }`}
              >
                {tab.name}
              </Link>
            ))}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<StrategyDashboard />} />
          <Route path="/backtest" element={<BacktestResults />} />
          <Route path="/optimization" element={<OptimizationDashboard />} />
          <Route path="/live" element={<LiveTrading />} />
          <Route path="/discovery" element={<VectorbtDiscovery />} />
          <Route path="/symbols" element={<SymbolOnboarding />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
