import { useEffect, useState } from 'react'
import { dashboardAPI } from '../api'

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
          onClick={() => setActiveTab('manage')}
          className={`px-4 py-2 font-semibold transition-colors ${
            activeTab === 'manage'
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
      </div>

      {/* Manage Tab */}
      {activeTab === 'manage' && (
        <div className="space-y-6">
          {/* Add Symbol Form */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Add Symbol</h3>
            <form onSubmit={handleAddSymbol} className="flex gap-3">
              <input
                type="text"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                placeholder="Enter symbol (e.g., EURUSD)"
                className="flex-1 px-4 py-2 bg-slate-700 text-white placeholder-slate-400 rounded border border-slate-600 focus:border-blue-500 focus:outline-none"
                disabled={refreshing}
              />
              <button
                type="submit"
                disabled={refreshing || !newSymbol.trim()}
                className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50 font-semibold"
              >
                Add
              </button>
            </form>
          </div>

          {/* Symbols List */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Available Symbols</h3>

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
                    {sym.results && (
                      <div className="mt-4 pt-4 border-t border-slate-600 grid grid-cols-2 gap-3">
                        <div>
                          <p className="text-xs text-slate-400">Best Strategy</p>
                          <p className="text-sm font-semibold text-white">{sym.results.best_strategy}</p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Profit Factor</p>
                          <p className={`text-sm font-semibold ${sym.results.profit_factor >= 1.2 ? 'text-green-400' : 'text-yellow-400'}`}>
                            {sym.results.profit_factor.toFixed(2)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Win Rate</p>
                          <p className="text-sm font-semibold text-white">{(sym.results.win_rate * 100).toFixed(1)}%</p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Sharpe Ratio</p>
                          <p className="text-sm font-semibold text-white">{sym.results.sharpe_ratio.toFixed(2)}</p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Total Trades</p>
                          <p className="text-sm font-semibold text-white">{sym.results.total_trades}</p>
                        </div>
                        <div>
                          <p className="text-xs text-slate-400">Validation</p>
                          <p className={`text-sm font-semibold ${sym.results.validated ? 'text-green-400' : 'text-yellow-400'}`}>
                            {sym.results.validated ? '✓ Validated' : 'Pending'}
                          </p>
                        </div>
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
