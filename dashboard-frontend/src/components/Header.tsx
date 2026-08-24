import { useEffect, useState } from 'react'
import { dashboardAPI } from '../api'
import { DashboardSummary } from '../types'

export default function Header() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadSummary = async () => {
      try {
        const data = await dashboardAPI.getSummary()
        setSummary(data)
      } catch (error) {
        console.error('Failed to load summary:', error)
      } finally {
        setLoading(false)
      }
    }

    loadSummary()
    const interval = setInterval(loadSummary, 10000) // Refresh every 10s
    return () => clearInterval(interval)
  }, [])

  return (
    <header className="bg-slate-900 border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-white">Trading Dashboard</h1>
            <p className="text-slate-400 text-sm mt-1">Strategy Performance & Optimization Analysis</p>
          </div>

          {loading ? (
            <div className="text-slate-400">Loading...</div>
          ) : summary ? (
            <div className="grid grid-cols-4 gap-6">
              <div className="text-center">
                <div className="text-2xl font-bold text-blue-400">{summary.total_strategies}</div>
                <div className="text-sm text-slate-400">Total Strategies</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-green-400">{summary.validated_strategies}</div>
                <div className="text-sm text-slate-400">Validated</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-yellow-400">{summary.avg_profit_factor.toFixed(2)}</div>
                <div className="text-sm text-slate-400">Avg PF</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-purple-400">
                  {summary.best_strategy?.pf?.toFixed(2) ?? 'N/A'}
                </div>
                <div className="text-sm text-slate-400">Best PF</div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  )
}
