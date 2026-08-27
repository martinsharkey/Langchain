import { useEffect, useState } from 'react'
import { dashboardAPI } from '../api'
import OnboardingWizard from '../components/OnboardingWizard'

interface SymbolStatus {
  symbol: string
  status: 'ready' | 'onboarding' | 'onboarded' | 'error'
  progress?: number
  results?: {
    best_strategy: string
    profit_factor: number
    win_rate: number
    sharpe_ratio: number
    total_trades: number
    validated: boolean
  }
  error?: string
  last_updated?: string
}

interface OnboardingTask {
  task_id: string
  symbol: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  started_at: string
  completed_at?: string
}

export default function SymbolOnboarding() {
  const [symbols, setSymbols] = useState<SymbolStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [activeTab, setActiveTab] = useState<'manage' | 'tasks'>('manage')
  const [tasks, setTasks] = useState<OnboardingTask[]>([])
  const [newSymbol, setNewSymbol] = useState('')
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [sessionPreferences, setSessionPreferences] = useState<Record<string, string[]>>({})
  const [showWizard, setShowWizard] = useState(false)
  const [symbolResults, setSymbolResults] = useState<Record<string, OnboardingResult[]>>({})
  const [resultsLoading, setResultsLoading] = useState<Record<string, boolean>>({})

  // Load symbols on mount
  useEffect(() => {
    loadSymbols()
    const interval = setInterval(loadSymbols, 5000)
    return () => clearInterval(interval)
  }, [])

  // Load tasks when tab changes
  useEffect(() => {
    if (activeTab === 'tasks') {
      loadTasks()
      const interval = setInterval(loadTasks, 3000)
      return () => clearInterval(interval)
    }
  }, [activeTab])

  // Fetch results when a symbol is selected.
  useEffect(() => {
    if (selectedSymbol && !symbolResults[selectedSymbol]) {
      fetchSymbolResults(selectedSymbol)
    }
  }, [selectedSymbol])

  const fetchSymbolResults = async (symbol: string) => {
    setResultsLoading((prev) => ({ ...prev, [symbol]: true }))
    try {
      const data = await dashboardAPI.getOnboardingResults(symbol)
      setSymbolResults((prev) => ({ ...prev, [symbol]: data }))
    } catch (error) {
      console.error(`Failed to load results for ${symbol}:`, error)
    } finally {
      setResultsLoading((prev) => ({ ...prev, [symbol]: false }))
    }
  }

  const loadSymbols = async () => {
    try {
      const data = await dashboardAPI.getSymbolStatuses()
      setSymbols(data)
      setLoading(false)
    } catch (error) {
      console.error('Failed to load symbols:', error)
      setLoading(false)
    }
  }

  const loadTasks = async () => {
    try {
      const data = await dashboardAPI.getOnboardingTasks()
      setTasks(data)
    } catch (error) {
      console.error('Failed to load tasks:', error)
    }
  }

  const handleOnboardSymbol = async (symbol: string) => {
    try {
      setRefreshing(true)
      const result = await dashboardAPI.onboardSymbol(symbol)
      console.log('Onboarding started:', result)
      
      // Immediately switch to tasks tab to see progress
      setActiveTab('tasks')
      
      // Start polling
      setTimeout(loadTasks, 1000)
    } catch (error) {
      console.error('Failed to onboard symbol:', error)
      alert(`Error onboarding ${symbol}: ${error}`)
    } finally {
      setRefreshing(false)
    }
  }

  const handleRemoveSymbol = async (symbol: string) => {
    if (!window.confirm(`Remove ${symbol} and all its data?`)) return

    try {
      setRefreshing(true)
      await dashboardAPI.removeSymbol(symbol)
      await loadSymbols()
    } catch (error) {
      console.error('Failed to remove symbol:', error)
      alert(`Error removing ${symbol}: ${error}`)
    } finally {
      setRefreshing(false)
    }
  }

  const handleRefreshSymbol = async (symbol: string) => {
    try {
      setRefreshing(true)
      const result = await dashboardAPI.refreshSymbol(symbol)
      console.log('Refresh started:', result)
      setActiveTab('tasks')
      setTimeout(loadTasks, 1000)
    } catch (error) {
      console.error('Failed to refresh symbol:', error)
      alert(`Error refreshing ${symbol}: ${error}`)
    } finally {
      setRefreshing(false)
    }
  }

  const handleAddSymbol = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newSymbol.trim()) return

    try {
      setRefreshing(true)
      const result = await dashboardAPI.addSymbol(newSymbol.toUpperCase())
      console.log('Symbol added:', result)
      setNewSymbol('')
      await loadSymbols()
    } catch (error) {
      console.error('Failed to add symbol:', error)
      alert(`Error adding ${newSymbol}: ${error}`)
    } finally {
      setRefreshing(false)
    }
  }

  const handleToggleSession = async (symbol: string, session: string) => {
    try {
      const current = sessionPreferences[symbol] || []
      const updated = current.includes(session)
        ? current.filter(s => s !== session)
        : [...current, session]
      
      // Save to backend
      await dashboardAPI.updateSessionPreferences(symbol, updated)
      
      // Update local state
      setSessionPreferences({
        ...sessionPreferences,
        [symbol]: updated,
      })
      
      console.log(`Session ${session} for ${symbol}: ${updated.includes(session) ? 'enabled' : 'disabled'}`)
    } catch (error) {
      console.error(`Failed to toggle session ${session}:`, error)
      alert(`Error updating session preferences: ${error}`)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'onboarded':
        return 'bg-green-500/20 text-green-400'
      case 'onboarding':
        return 'bg-blue-500/20 text-blue-400'
      case 'error':
        return 'bg-red-500/20 text-red-400'
      default:
        return 'bg-gray-500/20 text-gray-400'
    }
  }

  const getTaskStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-500/20 text-green-400'
      case 'running':
        return 'bg-blue-500/20 text-blue-400'
      case 'failed':
        return 'bg-red-500/20 text-red-400'
      case 'queued':
        return 'bg-yellow-500/20 text-yellow-400'
      default:
        return 'bg-gray-500/20 text-gray-400'
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-white">Symbol Onboarding</h2>
        <button
          onClick={loadSymbols}
          disabled={refreshing}
          className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded disabled:opacity-50"
        >
          {refreshing ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-4 border-b border-slate-700">
        <button
          onClick={() => { setActiveTab('manage'); setShowWizard(false) }}
          className={`px-4 py-2 font-semibold transition-colors ${
            activeTab === 'manage' && !showWizard
              ? 'text-white border-b-2 border-white'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Manage Symbols
        </button>
        <button
          onClick={() => setActiveTab('tasks')}
          className={`px-4 py-2 font-semibold transition-colors ${
            activeTab === 'tasks'
              ? 'text-white border-b-2 border-white'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Onboarding Tasks ({tasks.filter(t => t.status !== 'completed').length})
        </button>
        <button
          onClick={() => setShowWizard(true)}
          className={`px-4 py-2 font-semibold transition-colors ${
            showWizard
              ? 'text-white border-b-2 border-green-500'
              : 'text-green-400 hover:text-green-300'
          }`}
        >
          + Onboard New Symbol
        </button>
      </div>

      {/* Wizard */}
      {showWizard && (
        <OnboardingWizard onComplete={() => {
          setShowWizard(false)
          loadSymbols()
        }} />
      )}

      {/* Manage Tab */}
      {activeTab === 'manage' && !showWizard && (
        <div className="space-y-6">
          {/* Symbols List */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">Available Symbols</h3>
              <button
                onClick={() => setShowWizard(true)}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded font-semibold text-sm"
              >
                + Onboard New Symbol
              </button>
            </div>

            {loading ? (
              <div className="text-slate-400">Loading symbols...</div>
            ) : symbols.length === 0 ? (
              <div className="text-slate-400">No symbols yet. Add one to get started.</div>
            ) : (
              <div className="space-y-4">
                {symbols.map((sym) => (
                  <div
                    key={sym.symbol}
                    className="bg-slate-700/50 rounded-lg p-4 border border-slate-600"
                    onClick={() => setSelectedSymbol(selectedSymbol === sym.symbol ? null : sym.symbol)}
                    role="button"
                    tabIndex={0}
                  >
                    {/* Header */}
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <h4 className="text-lg font-semibold text-white">{sym.symbol}</h4>
                        <p className="text-sm text-slate-400">
                          {sym.last_updated ? `Updated: ${new Date(sym.last_updated).toLocaleString()}` : 'Never'}
                        </p>
                      </div>
                      <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${getStatusColor(sym.status)}`}>
                        {sym.status === 'onboarding' && sym.progress ? `${sym.progress}%` : sym.status}
                      </span>
                    </div>

                    {/* Results (if available) */}
                    {selectedSymbol === sym.symbol && (
                      <div className="mt-4 pt-4 border-t border-slate-600 space-y-4">
                        {resultsLoading[sym.symbol] && (
                          <p className="text-sm text-slate-400">Loading results...</p>
                        )}
                        {!resultsLoading[sym.symbol] && symbolResults[sym.symbol] && symbolResults[sym.symbol].length > 0 && (
                          <>
                            <div className="flex items-center justify-between">
                              <p className="text-xs text-slate-400">
                                📊 {symbolResults[sym.symbol].length} strategy combinations found
                              </p>
                              <span className="text-xs text-slate-500">
                                £{symbolResults[sym.symbol][0]?.start_balance.toFixed(0)} → best £{Math.max(...symbolResults[sym.symbol].map(r => r.end_balance)).toFixed(0)}
                              </span>
                            </div>
                            <div className="overflow-x-auto max-h-64 overflow-y-auto">
                              <table className="w-full text-xs">
                                <thead className="sticky top-0 bg-slate-700">
                                  <tr className="text-left text-slate-400">
                                    <th className="py-1 pr-2">Session</th>
                                    <th className="py-1 pr-2">TF</th>
                                    <th className="py-1 pr-2">Indicator</th>
                                    <th className="py-1 pr-2">Lib</th>
                                    <th className="py-1 pr-2">Score</th>
                                    <th className="py-1 pr-2">Trades</th>
                                    <th className="py-1 pr-2">PF</th>
                                    <th className="py-1 pr-2">Sharpe</th>
                                    <th className="py-1 pr-2">DD</th>
                                    <th className="py-1 pr-2">£100→</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {symbolResults[sym.symbol]
                                    .sort((a, b) => b.score - a.score)
                                    .slice(0, 20)
                                    .map((r, i) => (
                                      <tr key={i} className="border-t border-slate-700/50">
                                        <td className="py-1 pr-2 text-slate-300">{r.session_display}</td>
                                        <td className="py-1 pr-2 text-slate-300">{r.timeframe}</td>
                                        <td className="py-1 pr-2 text-white font-medium">{r.indicator.length > 20 ? r.indicator.slice(0, 20) + '…' : r.indicator}</td>
                                        <td className="py-1 pr-2 text-slate-500">{r.library}</td>
                                        <td className="py-1 pr-2 text-slate-300">{r.score.toFixed(3)}</td>
                                        <td className="py-1 pr-2 text-slate-300">{r.trades}</td>
                                        <td className={`py-1 pr-2 ${r.profit_factor >= 1.2 ? 'text-green-400' : r.profit_factor >= 1 ? 'text-blue-400' : 'text-yellow-400'}`}>
                                          {r.profit_factor === Infinity ? 'inf' : r.profit_factor.toFixed(2)}
                                        </td>
                                        <td className="py-1 pr-2 text-slate-300">{r.sharpe === Infinity ? 'inf' : r.sharpe.toFixed(2)}</td>
                                        <td className="py-1 pr-2 text-red-400">{(r.max_drawdown * 100).toFixed(1)}%</td>
                                        <td className={`py-1 pr-2 ${r.end_balance >= 100 ? 'text-green-400' : 'text-red-400'}`}>
                                          £{r.end_balance.toFixed(0)}
                                        </td>
                                      </tr>
                                    ))}
                                </tbody>
                              </table>
                            </div>
                            {symbolResults[sym.symbol].length > 20 && (
                              <p className="text-xs text-slate-500">Showing top 20 of {symbolResults[sym.symbol].length}. Download JSON for all.</p>
                            )}
                          </>
                        )}
                        {!resultsLoading[sym.symbol] && (!symbolResults[sym.symbol] || symbolResults[sym.symbol].length === 0) && sym.status === 'onboarded' && (
                          <p className="text-sm text-slate-400">No viable strategies found for this symbol.</p>
                        )}
                      </div>
                     )}

                    {/* Error Message */}
                    {sym.error && (
                      <div className="mt-4 pt-4 border-t border-slate-600">
                        <p className="text-sm text-red-400">{sym.error}</p>
                      </div>
                    )}

                    {/* Actions */}
                    <div className="mt-4 flex gap-2">
                      {sym.status === 'ready' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleOnboardSymbol(sym.symbol)
                          }}
                          disabled={refreshing}
                          className="flex-1 px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50 text-sm font-semibold"
                        >
                          🚀 Onboard Symbol
                        </button>
                      )}
                      {sym.status === 'onboarding' && (
                        <div className="flex-1 px-3 py-2 bg-blue-600/50 text-blue-300 rounded text-sm font-semibold flex items-center justify-center">
                          ⏳ Onboarding in progress...
                        </div>
                      )}
                      {sym.status === 'onboarded' && (
                        <>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleRefreshSymbol(sym.symbol)
                            }}
                            disabled={refreshing}
                            className="flex-1 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50 text-sm font-semibold"
                          >
                            🔄 Refresh
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleRemoveSymbol(sym.symbol)
                            }}
                            disabled={refreshing}
                            className="flex-1 px-3 py-2 bg-red-600 hover:bg-red-700 text-white rounded disabled:opacity-50 text-sm font-semibold"
                          >
                            🗑️ Remove
                          </button>
                        </>
                      )}
                      {sym.status === 'error' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleOnboardSymbol(sym.symbol)
                          }}
                          disabled={refreshing}
                          className="flex-1 px-3 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded disabled:opacity-50 text-sm font-semibold"
                        >
                          ⚠️ Retry
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tasks Tab */}
      {activeTab === 'tasks' && (
        <div className="space-y-4">
          {tasks.length === 0 ? (
            <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 text-slate-400">
              No onboarding tasks yet
            </div>
          ) : (
            tasks.map((task) => (
              <div
                key={task.task_id}
                className="bg-slate-800 rounded-lg border border-slate-700 p-4"
              >
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h4 className="font-semibold text-white">{task.symbol}</h4>
                    <p className="text-sm text-slate-400">
                      Started: {new Date(task.started_at).toLocaleString()}
                    </p>
                  </div>
                  <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${getTaskStatusColor(task.status)}`}>
                    {task.status}
                  </span>
                </div>

                {/* Message */}
                <p className="text-sm text-slate-300 mb-3">{task.message}</p>

                {/* Progress Bar */}
                <div className="w-full bg-slate-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all ${
                      task.status === 'completed'
                        ? 'bg-green-500'
                        : task.status === 'failed'
                        ? 'bg-red-500'
                        : task.status === 'running'
                        ? 'bg-blue-500'
                        : 'bg-yellow-500'
                    }`}
                    style={{ width: `${task.progress}%` }}
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1">{task.progress}%</p>

                {/* Completion Time */}
                {task.completed_at && (
                  <p className="text-xs text-slate-400 mt-2">
                    Completed: {new Date(task.completed_at).toLocaleString()}
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
