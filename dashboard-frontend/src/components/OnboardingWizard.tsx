/**
 * OnboardingWizard — multi-step wizard for onboarding a symbol into the
 * VectorBT pipeline. Uses native VectorBT for all backtesting; the UI only
 * configures and observes.
 */

import { useCallback, useEffect, useState } from 'react'
import { dashboardAPI } from '../api'
import type {
  LiveSymbol,
  OnboardingResult,
  ProgressMarker,
  WizardSession,
  WizardTimeframe,
} from '../types'

// --- Static config (display names + descriptions for the UI) ---

const SESSIONS: WizardSession[] = [
  { key: 'asian', name: 'Asian Session', window: '00:00–08:00 UTC', days: 'Mon–Fri', description: 'Tokyo/HK/Singapore. Range-bound, wider spreads. Favours mean-reversion.' },
  { key: 'london', name: 'London Session', window: '08:00–17:00 UTC', days: 'Mon–Fri', description: 'Highest FX liquidity. Directional moves, tightest spreads. Trend-following excels.' },
  { key: 'newyork', name: 'New York Session', window: '13:00–21:00 UTC', days: 'Mon–Fri', description: 'US participants enter. Overlaps London early. NFP/FOMC land here.' },
  { key: 'overlap_asia_london', name: 'Asia–London Overlap', window: '07:00–09:00 UTC', days: 'Mon–Fri', description: 'Tokyo close meets London open. Transition window for range breaks.' },
  { key: 'overlap_london_ny', name: 'London–NY Overlap', window: '13:00–17:00 UTC', days: 'Mon–Fri', description: 'Highest volatility window. Both centres fully open. Strongest edge for breakouts.' },
  { key: 'market_open_15', name: 'Post-Market Open (15m)', window: '22:00–22:15 UTC', days: 'Mon–Thu', description: 'First 15 min after open. Order books reset. Volatile, directionally biased.' },
  { key: 'market_open_30', name: 'Post-Market Open (30m)', window: '22:00–22:30 UTC', days: 'Mon–Thu', description: 'First 30 min after open. Opening momentum window.' },
  { key: 'market_open_60', name: 'Post-Market Open (60m)', window: '22:00–23:00 UTC', days: 'Mon–Thu', description: 'First 60 min after open. Extended opening effect.' },
  { key: 'weekly_close', name: 'Weekly Close', window: '22:00–23:00 UTC', days: 'Mon–Thu', description: 'End-of-day position squaring. Mean-reverting, widening spreads.' },
  { key: 'sunday_open', name: 'Sunday Open', window: '22:00–24:00 UTC', days: 'Sunday', description: 'New week open. First institutional flow after the weekend gap.' },
  { key: 'friday_close', name: 'Friday Close', window: '21:00–22:00 UTC', days: 'Friday', description: 'Pre-weekend positioning. Transition to crypto weekend session.' },
  { key: 'weekend', name: 'BTCUSD Weekend', window: 'Fri 22:00–Sun 21:00 UTC', days: 'Fri–Sun', description: 'Crypto never sleeps. Retail-driven. Can spike violently. Crypto-only.' },
]

const TIMEFRAMES: WizardTimeframe[] = [
  { key: 'M1', name: '1 Minute', description: 'Highest resolution. Most bars, longest test. Best for scalping.' },
  { key: 'M5', name: '5 Minutes', description: 'Popular intraday. Good balance of noise and speed.' },
  { key: 'M15', name: '15 Minutes', description: 'Standard intraday. Cleaner signals than M1/M5.' },
  { key: 'M30', name: '30 Minutes', description: 'Medium-term intraday. Fewer trades, higher quality.' },
  { key: 'H1', name: '1 Hour', description: 'Swing trading. Less history needed for meaningful results.' },
  { key: 'H4', name: '4 Hours', description: 'Multi-day swing. Fewer trades per test period.' },
  { key: 'D1', name: 'Daily', description: 'Long-term positional. Fewest bars, fastest test.' },
]

const STEPS = ['Symbol', 'Sessions', 'Timeframes', 'Period', 'Summary'] as const
type Step = (typeof STEPS)[number]

export default function OnboardingWizard({ onComplete }: { onComplete?: () => void }) {
  const [step, setStep] = useState<Step>('Symbol')
  const [symbols, setSymbols] = useState<LiveSymbol[]>([])
  const [symbolsLoading, setSymbolsLoading] = useState(false)
  const [selectedSymbol, setSelectedSymbol] = useState('')
  const [selectedSessions, setSelectedSessions] = useState<string[]>([])
  const [selectedTimeframes, setSelectedTimeframes] = useState<string[]>([])
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // --- Live onboarding state ---
  const [onboarding, setOnboarding] = useState(false)
  const [progress, setProgress] = useState<ProgressMarker[]>([])
  const [results, setResults] = useState<OnboardingResult[]>([])
  const [taskId, setTaskId] = useState<string | null>(null)

  const stepIndex = STEPS.indexOf(step)

  // --- Load MT5 symbols ---
  const loadSymbols = useCallback(async () => {
    setSymbolsLoading(true)
    try {
      const data = await dashboardAPI.getLiveSymbols()
      setSymbols(data)
    } catch (e) {
      setError(`Failed to load symbols: ${e}`)
    } finally {
      setSymbolsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSymbols()
  }, [loadSymbols])

  // --- Selection helpers ---
  const toggleSession = (key: string) => {
    setSelectedSessions((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }
  const toggleTimeframe = (key: string) => {
    setSelectedTimeframes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }
  const selectAllSessions = () => setSelectedSessions(SESSIONS.map((s) => s.key))
  const selectAllTimeframes = () => setSelectedTimeframes(TIMEFRAMES.map((t) => t.key))

  // --- Navigation ---
  const canNext = (): boolean => {
    switch (step) {
      case 'Symbol': return selectedSymbol !== ''
      case 'Sessions': return selectedSessions.length > 0
      case 'Timeframes': return selectedTimeframes.length > 0
      case 'Period': return startDate !== '' && endDate !== ''
      case 'Summary': return true
      default: return false
    }
  }
  const next = () => {
    if (!canNext()) return
    const idx = STEPS.indexOf(step)
    if (idx < STEPS.length - 1) setStep(STEPS[idx + 1])
  }
  const back = () => {
    const idx = STEPS.indexOf(step)
    if (idx > 0) setStep(STEPS[idx - 1])
  }

  // --- Estimate ---
  const estimateSeconds = (): number => {
    const nIndicators = 352
    const avgOccurrences = 5
    return selectedSessions.length * selectedTimeframes.length * nIndicators * avgOccurrences * 0.05
  }
  const formatEstimate = (secs: number): string => {
    if (secs < 60) return `${Math.round(secs)}s`
    if (secs < 3600) return `${Math.round(secs / 60)} min`
    return `${(secs / 3600).toFixed(1)} hrs`
  }

  // --- Start onboarding ---
  const startOnboarding = async () => {
    setStarting(true)
    setError(null)
    try {
      const res = await dashboardAPI.startOnboarding(selectedSymbol, {
        sessions: selectedSessions,
        timeframes: selectedTimeframes,
        start_date: startDate,
        end_date: endDate,
        top_n: 10,
      })
      setTaskId(res.task_id)
      setOnboarding(true)
    } catch (e) {
      setError(`Failed to start: ${e}`)
    } finally {
      setStarting(false)
    }
  }

  // --- Poll progress + results while onboarding ---
  useEffect(() => {
    if (!onboarding || !selectedSymbol) return
    const interval = setInterval(async () => {
      try {
        const [prog, res] = await Promise.all([
          dashboardAPI.getOnboardingProgress(selectedSymbol),
          dashboardAPI.getOnboardingResults(selectedSymbol),
        ])
        setProgress(prog)
        setResults(res)
        // Stop polling if complete.
        const last = prog[prog.length - 1]
        if (last && (last.type === 'complete' || last.type === 'cancelled')) {
          clearInterval(interval)
        }
      } catch {
        // Poll errors are non-fatal.
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [onboarding, selectedSymbol])

  const latestProgress = progress[progress.length - 1]
  const isComplete = latestProgress?.type === 'complete'
  const progressPct = (() => {
    if (isComplete) return 100
    if (!latestProgress?.combinations_completed || !latestProgress?.total_combinations) return 0
    return Math.round((latestProgress.combinations_completed / latestProgress.total_combinations) * 100)
  })()

  // --- Render ---
  if (onboarding) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-bold text-white">Onboarding {selectedSymbol}</h2>
          {isComplete && (
            <span className="px-3 py-1 rounded-full text-sm font-semibold bg-green-500/20 text-green-400">Complete</span>
          )}
        </div>

        {/* Progress bar */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
          <div className="flex justify-between text-sm text-slate-400 mb-2">
            <span>
              {latestProgress?.type === "combination_complete"
                ? `${latestProgress.timeframe}:${latestProgress.session}`
                : latestProgress?.type === "complete"
                ? "Finished"
                : "Starting..."}
            </span>
            <span>{progressPct}%</span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-3">
            <div
              className={`h-3 rounded-full transition-all ${isComplete ? 'bg-green-500' : 'bg-blue-500'}`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {latestProgress?.results_count != null && (
            <p className="text-xs text-slate-400 mt-2">{latestProgress.results_count} strategy combinations found</p>
          )}
        </div>

        {/* Live results table */}
        {results.length > 0 && (
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
            <h3 className="text-lg font-semibold text-white mb-3">Live Results</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-400 border-b border-slate-700">
                    <th className="pb-2 pr-3">Session</th>
                    <th className="pb-2 pr-3">TF</th>
                    <th className="pb-2 pr-3">Indicator</th>
                    <th className="pb-2 pr-3">Lib</th>
                    <th className="pb-2 pr-3">Score</th>
                    <th className="pb-2 pr-3">Trades</th>
                    <th className="pb-2 pr-3">PF</th>
                    <th className="pb-2 pr-3">Sharpe</th>
                    <th className="pb-2 pr-3">DD</th>
                    <th className="pb-2 pr-3">£100→</th>
                  </tr>
                </thead>
                <tbody>
                  {results
                    .sort((a, b) => b.score - a.score)
                    .slice(0, 50)
                    .map((r, i) => (
                      <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                        <td className="py-1.5 pr-3 text-slate-300">{r.session_display}</td>
                        <td className="py-1.5 pr-3 text-slate-300">{r.timeframe}</td>
                        <td className="py-1.5 pr-3 text-white font-medium">{r.indicator}</td>
                        <td className="py-1.5 pr-3 text-slate-400 text-xs">{r.library}</td>
                        <td className="py-1.5 pr-3 text-slate-300">{r.score.toFixed(3)}</td>
                        <td className="py-1.5 pr-3 text-slate-300">{r.trades}</td>
                        <td className={`py-1.5 pr-3 ${r.profit_factor >= 1.2 ? 'text-green-400' : r.profit_factor >= 1.0 ? 'text-blue-400' : 'text-yellow-400'}`}>
                      {r.profit_factor.toFixed(2)}
                    </td>
                    <td className="py-1.5 pr-3 text-slate-300">{r.sharpe.toFixed(2)}</td>
                    <td className="py-1.5 pr-3 text-red-400">{(r.max_drawdown * 100).toFixed(1)}%</td>
                    <td className={`py-1.5 pr-3 ${r.end_balance >= 100 ? 'text-green-400' : 'text-red-400'}`}>
                      £{r.end_balance.toFixed(0)}
                    </td>
                  </tr>
                ))}
                </tbody>
              </table>
            </div>
            {results.length > 50 && (
              <p className="text-xs text-slate-500 mt-2">Showing top 50 of {results.length} results. Download the full JSON for all.</p>
            )}
          </div>
        )}

        {/* Download */}
        {isComplete && (
          <div className="flex gap-3">
            <a
              href={`/api/onboarding/${selectedSymbol}/download`}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded font-semibold"
              download
            >
              Download Raw JSON
            </a>
            <button
              onClick={() => {
                setOnboarding(false)
                setProgress([])
                setResults([])
                setTaskId(null)
                onComplete?.()
              }}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded font-semibold"
            >
              Done
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-white">Onboard New Symbol</h2>

      {/* Stepper */}
      <div className="flex gap-2">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              i <= stepIndex ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'
            }`}>{i + 1}</div>
            <span className={`text-sm ${i === stepIndex ? 'text-white font-semibold' : 'text-slate-400'}`}>{s}</span>
            {i < STEPS.length - 1 && <span className="text-slate-600">→</span>}
          </div>
        ))}
      </div>

      {error && <div className="bg-red-500/20 text-red-400 rounded p-3">{error}</div>}

      {/* Step content */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
        {step === 'Symbol' && (
          <div className="space-y-4">
            <div className="flex gap-3 items-end">
              <div className="flex-1">
                <label className="block text-sm text-slate-400 mb-1">Symbol</label>
                <select
                  value={selectedSymbol}
                  onChange={(e) => setSelectedSymbol(e.target.value)}
                  className="w-full px-4 py-2 bg-slate-700 text-white rounded border border-slate-600 focus:border-blue-500 focus:outline-none"
                >
                  <option value="">Select a symbol...</option>
                  {symbols.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name} — {s.description}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={loadSymbols}
                disabled={symbolsLoading}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded disabled:opacity-50"
              >
                {symbolsLoading ? 'Loading...' : 'Refresh'}
              </button>
            </div>
            {symbols.length > 0 && (
              <p className="text-xs text-slate-500">{symbols.length} symbols available from MT5</p>
            )}
          </div>
        )}

        {step === 'Sessions' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white">Select Sessions</h3>
              <button onClick={selectAllSessions} className="text-sm text-blue-400 hover:text-blue-300">Select All</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {SESSIONS.map((s) => (
                <label
                  key={s.key}
                  className={`flex items-start gap-3 p-3 rounded border cursor-pointer transition-colors ${
                    selectedSessions.includes(s.key) ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600 hover:border-slate-500'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedSessions.includes(s.key)}
                    onChange={() => toggleSession(s.key)}
                    className="mt-1 w-4 h-4 rounded accent-blue-500"
                  />
                  <div>
                    <p className="text-white font-medium">{s.name}</p>
                    <p className="text-xs text-slate-400">{s.window} · {s.days}</p>
                    <p className="text-xs text-slate-500 mt-1">{s.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}

        {step === 'Timeframes' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white">Select Timeframes</h3>
              <button onClick={selectAllTimeframes} className="text-sm text-blue-400 hover:text-blue-300">Select All</button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {TIMEFRAMES.map((t) => (
                <label
                  key={t.key}
                  className={`flex items-start gap-3 p-3 rounded border cursor-pointer transition-colors ${
                    selectedTimeframes.includes(t.key) ? 'border-blue-500 bg-blue-500/10' : 'border-slate-600 hover:border-slate-500'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedTimeframes.includes(t.key)}
                    onChange={() => toggleTimeframe(t.key)}
                    className="mt-1 w-4 h-4 rounded accent-blue-500"
                  />
                  <div>
                    <p className="text-white font-medium">{t.name}</p>
                    <p className="text-xs text-slate-500">{t.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}

        {step === 'Period' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-white">Test Period</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full px-4 py-2 bg-slate-700 text-white rounded border border-slate-600 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full px-4 py-2 bg-slate-700 text-white rounded border border-slate-600 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>
            {startDate && endDate && (
              <p className="text-sm text-slate-400">
                Estimated test time: <span className="text-white font-semibold">{formatEstimate(estimateSeconds())}</span>
                <span className="text-slate-500"> ({selectedSessions.length} sessions × {selectedTimeframes.length} timeframes × 352 indicators)</span>
              </p>
            )}
          </div>
        )}

        {step === 'Summary' && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-white">Confirm Onboarding</h3>
            <div className="space-y-2 text-sm">
              <p><span className="text-slate-400">Symbol:</span> <span className="text-white font-semibold">{selectedSymbol}</span></p>
              <p><span className="text-slate-400">Sessions:</span> <span className="text-white">{selectedSessions.length} selected</span></p>
              <p><span className="text-slate-400">Timeframes:</span> <span className="text-white">{selectedTimeframes.length} selected</span></p>
              <p><span className="text-slate-400">Period:</span> <span className="text-white">{startDate || '—'} → {endDate || '—'}</span></p>
              <p><span className="text-slate-400">Estimated time:</span> <span className="text-white font-semibold">{formatEstimate(estimateSeconds())}</span></p>
              <p><span className="text-slate-400">Start balance:</span> <span className="text-green-400 font-semibold">£100</span></p>
            </div>
            <button
              onClick={startOnboarding}
              disabled={starting}
              className="px-6 py-3 bg-green-600 hover:bg-green-700 text-white rounded font-bold disabled:opacity-50"
            >
              {starting ? 'Starting...' : 'Start Onboarding'}
            </button>
          </div>
        )}
      </div>

      {/* Nav buttons */}
      <div className="flex justify-between">
        <button
          onClick={back}
          disabled={stepIndex === 0}
          className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded disabled:opacity-50"
        >
          Back
        </button>
        {step !== 'Summary' && (
          <button
            onClick={next}
            disabled={!canNext()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50 font-semibold"
          >
            Next
          </button>
        )}
      </div>
    </div>
  )
}
