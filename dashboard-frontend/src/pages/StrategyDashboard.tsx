import { useEffect, useState } from 'react'
import { dashboardAPI } from '../api'
import { Strategy } from '../types'

export default function StrategyDashboard() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    const loadStrategies = async () => {
      try {
        const data = await dashboardAPI.listStrategies()
        setStrategies(data)
        if (data.length > 0) {
          setSelectedStrategy(data[0])
        }
      } catch (error) {
        console.error('Failed to load strategies:', error)
      } finally {
        setLoading(false)
      }
    }

    loadStrategies()
  }, [])

  const filteredStrategies =
    filter === 'validated' ? strategies.filter((s) => s.validated) : strategies

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <div className="bg-gradient-to-r from-blue-600/20 to-purple-600/20 border border-blue-500/30 rounded-lg p-8">
        <h2 className="text-2xl font-bold text-white mb-4">Strategy Performance Overview</h2>
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-slate-800/50 rounded p-4">
            <div className="text-3xl font-bold text-blue-400">{strategies.length}</div>
            <div className="text-sm text-slate-400 mt-1">Total Strategies</div>
          </div>
          <div className="bg-slate-800/50 rounded p-4">
            <div className="text-3xl font-bold text-green-400">
              {strategies.filter((s) => s.validated).length}
            </div>
            <div className="text-sm text-slate-400 mt-1">Validated</div>
          </div>
          <div className="bg-slate-800/50 rounded p-4">
            <div className="text-3xl font-bold text-yellow-400">
              {(
                strategies.reduce((sum, s) => sum + (s.vectorbt_pf || 0), 0) /
                strategies.length
              ).toFixed(2)}
            </div>
            <div className="text-sm text-slate-400 mt-1">Avg PF</div>
          </div>
          <div className="bg-slate-800/50 rounded p-4">
            <div className="text-3xl font-bold text-purple-400">
              {Math.max(...strategies.map((s) => s.vectorbt_pf || 0)).toFixed(2)}
            </div>
            <div className="text-sm text-slate-400 mt-1">Best PF</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Left: Strategy Table */}
        <div className="col-span-2">
          <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-700 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white">All Strategies</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => setFilter('all')}
                  className={`px-3 py-1 rounded text-sm ${
                    filter === 'all'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                  }`}
                >
                  All
                </button>
                <button
                  onClick={() => setFilter('validated')}
                  className={`px-3 py-1 rounded text-sm ${
                    filter === 'validated'
                      ? 'bg-green-600 text-white'
                      : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                  }`}
                >
                  Validated Only
                </button>
              </div>
            </div>

            {loading ? (
              <div className="p-6 text-center text-slate-400">Loading...</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-700/50">
                    <tr>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-slate-400">
                        Strategy
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-slate-400">
                        Symbol
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-slate-400">
                        PF
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-slate-400">
                        WR
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-slate-400">
                        Sharpe
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-slate-400">
                        Trades
                      </th>
                      <th className="px-6 py-3 text-left text-sm font-semibold text-slate-400">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700">
                    {filteredStrategies.map((strategy) => (
                      <tr
                        key={`${strategy.symbol}-${strategy.name}`}
                        onClick={() => setSelectedStrategy(strategy)}
                        className="hover:bg-slate-700/50 cursor-pointer transition-colors"
                      >
                        <td className="px-6 py-3 text-sm font-medium text-white">
                          {strategy.name}
                        </td>
                        <td className="px-6 py-3 text-sm text-slate-400">{strategy.symbol}</td>
                        <td className="px-6 py-3 text-sm">
                          {strategy.vectorbt_pf ? (
                            <span
                              className={
                                strategy.vectorbt_pf > 1.2
                                  ? 'text-green-400 font-semibold'
                                  : strategy.vectorbt_pf > 1.0
                                  ? 'text-yellow-400'
                                  : 'text-red-400'
                              }
                            >
                              {strategy.vectorbt_pf.toFixed(2)}
                            </span>
                          ) : (
                            <span className="text-slate-500">-</span>
                          )}
                        </td>
                        <td className="px-6 py-3 text-sm">
                          {strategy.backtest?.wr ? (
                            <span
                              className={
                                strategy.backtest.wr > 0.5
                                  ? 'text-green-400'
                                  : 'text-orange-400'
                              }
                            >
                              {(strategy.backtest.wr * 100).toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-slate-500">-</span>
                          )}
                        </td>
                        <td className="px-6 py-3 text-sm text-slate-400">
                          {strategy.backtest?.sharpe?.toFixed(2) ?? '-'}
                        </td>
                        <td className="px-6 py-3 text-sm text-slate-400">
                          {strategy.backtest?.trades ?? '-'}
                        </td>
                        <td className="px-6 py-3 text-sm">
                          {strategy.validated ? (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400">
                              ✓ Validated
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-500/20 text-gray-400">
                              Pending
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right: Strategy Detail */}
        <div className="col-span-1">
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 sticky top-24">
            {selectedStrategy ? (
              <div className="space-y-6">
                <div>
                  <h4 className="text-lg font-semibold text-white mb-2">
                    {selectedStrategy.name}
                  </h4>
                  <p className="text-sm text-slate-400">{selectedStrategy.symbol}</p>
                </div>

                {selectedStrategy.backtest && (
                  <div className="space-y-3 border-t border-slate-700 pt-4">
                    <h5 className="text-sm font-semibold text-slate-300">Backtest</h5>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-400">Profit Factor</span>
                        <span className="text-sm font-semibold text-blue-400">
                          {selectedStrategy.backtest.pf.toFixed(2)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-400">Win Rate</span>
                        <span className="text-sm font-semibold text-green-400">
                          {(selectedStrategy.backtest.wr * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-400">Sharpe Ratio</span>
                        <span className="text-sm font-semibold text-yellow-400">
                          {selectedStrategy.backtest.sharpe.toFixed(2)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-400">Trades</span>
                        <span className="text-sm font-semibold text-slate-300">
                          {selectedStrategy.backtest.trades}
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {selectedStrategy.regime_edges.length > 0 && (
                  <div className="space-y-3 border-t border-slate-700 pt-4">
                    <h5 className="text-sm font-semibold text-slate-300">Regime Edges</h5>
                    <div className="space-y-2">
                      {selectedStrategy.regime_edges.map((edge) => (
                        <div key={edge.regime} className="flex justify-between">
                          <span className="text-sm text-slate-400 capitalize">
                            {edge.regime}
                          </span>
                          <span
                            className={`text-sm font-semibold ${
                              edge.multiplier > 1.1
                                ? 'text-green-400'
                                : edge.multiplier > 1.0
                                ? 'text-yellow-400'
                                : 'text-red-400'
                            }`}
                          >
                            {edge.multiplier.toFixed(2)}x
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {selectedStrategy.live && (
                  <div className="space-y-3 border-t border-slate-700 pt-4">
                    <h5 className="text-sm font-semibold text-slate-300">Live Performance</h5>
                    <div className="space-y-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-400">Trades</span>
                        <span className="text-sm font-semibold text-slate-300">
                          {selectedStrategy.live.trades}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-400">P&L</span>
                        <span
                          className={`text-sm font-semibold ${
                            selectedStrategy.live.pnl > 0 ? 'text-green-400' : 'text-red-400'
                          }`}
                        >
                          ${selectedStrategy.live.pnl.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center text-slate-400">Select a strategy to view details</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
