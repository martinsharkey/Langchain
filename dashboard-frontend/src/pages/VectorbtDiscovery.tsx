import { useEffect, useState } from 'react'
import { dashboardAPI } from '../api'
import { VectorbtDiscovery } from '../types'

export default function VectorbtDiscovery() {
  const [discovery, setDiscovery] = useState<VectorbtDiscovery | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadDiscovery = async () => {
      try {
        const data = await dashboardAPI.getVectorbtDiscovery()
        setDiscovery(data)
      } catch (error) {
        console.error('Failed to load discovery:', error)
      } finally {
        setLoading(false)
      }
    }

    loadDiscovery()
  }, [])

  return (
    <div className="space-y-8">
      <h2 className="text-2xl font-bold text-white">Vectorbt Edge Discovery</h2>

      {loading ? (
        <div className="text-slate-400">Loading...</div>
      ) : discovery ? (
        <div className="space-y-6">
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Discovery Status</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-sm text-slate-400">Last Sweep:</span>
                <p className="text-white font-semibold">
                  {new Date(discovery.swept_at).toLocaleString()}
                </p>
              </div>
              <div>
                <span className="text-sm text-slate-400">Min PF Threshold:</span>
                <p className="text-white font-semibold">{discovery.min_pf_threshold.toFixed(2)}</p>
              </div>
              <div>
                <span className="text-sm text-slate-400">Timeframe:</span>
                <p className="text-white font-semibold">{discovery.timeframe}</p>
              </div>
            </div>
          </div>

          <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Per-Symbol Validation</h3>
            <div className="space-y-3">
              {Object.entries(discovery.symbols).map(([symbol, data]) => (
                <div key={symbol} className="flex items-center justify-between p-3 bg-slate-700/50 rounded">
                  <div>
                    <p className="font-semibold text-white">{symbol}</p>
                    <p className="text-sm text-slate-400">{data.pockets} pocket(s)</p>
                  </div>
                  <div>
                    {data.validated ? (
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold bg-green-500/20 text-green-400">
                        ✓ Validated
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold bg-gray-500/20 text-gray-400">
                        Pending
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
          <p className="text-slate-400">No discovery data available</p>
        </div>
      )}
    </div>
  )
}
