import axios from 'axios'
import {
  Strategy,
  BacktestResult,
  VectorbtDiscovery,
  DashboardSummary,
  ApiResponse,
} from './types'

const API_BASE = '/api'
const API_V2_BASE = '/api/v2'

const api = axios.create({
  baseURL: API_V2_BASE,
  timeout: 10000,
})

const apiRoot = axios.create({
  baseURL: API_BASE,
  timeout: 30000, // Longer timeout for symbol operations
})

// Add request interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

apiRoot.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Root Error:', error)
    return Promise.reject(error)
  }
)

export const dashboardAPI = {
  /**
   * List all strategies with metrics
   */
  listStrategies: async (symbol?: string, sort?: string): Promise<Strategy[]> => {
    const response = await api.get<ApiResponse<Strategy[]>>('/strategies', {
      params: { symbol, sort },
    })
    return response.data.data
  },

  /**
   * Get detailed strategy metrics
   */
  getStrategy: async (name: string): Promise<Strategy> => {
    const response = await api.get<ApiResponse<Strategy>>(
      `/strategies/${encodeURIComponent(name)}`
    )
    return response.data.data
  },

  /**
   * Get backtest results
   */
  getBacktestResults: async (
    symbol?: string,
    strategy?: string
  ): Promise<BacktestResult[]> => {
    const response = await api.get<ApiResponse<BacktestResult[]>>(
      '/backtest/results',
      {
        params: { symbol, strategy },
      }
    )
    return response.data.data
  },

  /**
   * Get vectorbt edge discovery results
   */
  getVectorbtDiscovery: async (): Promise<VectorbtDiscovery> => {
    const response = await api.get<ApiResponse<VectorbtDiscovery>>(
      '/vectorbt/discovery'
    )
    return response.data.data
  },

  /**
   * Get dashboard summary statistics
   */
  getSummary: async (): Promise<DashboardSummary> => {
    const response = await api.get<ApiResponse<DashboardSummary>>('/summary')
    return response.data.data
  },

  // Symbol Management API
  /**
   * Get all symbol statuses
   */
  getSymbolStatuses: async () => {
    const response = await apiRoot.get('/symbols')
    return response.data.symbols || []
  },

  /**
   * Get status of a specific symbol
   */
  getSymbolStatus: async (symbol: string) => {
    const response = await apiRoot.get(`/symbols/${symbol}`)
    return response.data
  },

  /**
   * Start onboarding for a symbol
   */
  onboardSymbol: async (symbol: string) => {
    const response = await apiRoot.post(`/symbols/${symbol}/onboard`)
    return response.data
  },

  /**
   * Refresh/re-run onboarding for a symbol
   */
  refreshSymbol: async (symbol: string) => {
    const response = await apiRoot.post(`/symbols/${symbol}/refresh`)
    return response.data
  },

  /**
   * Remove a symbol
   */
  removeSymbol: async (symbol: string) => {
    const response = await apiRoot.delete(`/symbols/${symbol}`)
    return response.data
  },

  /**
   * Add a new symbol
   */
  addSymbol: async (symbol: string) => {
    const response = await apiRoot.post('/symbols', { symbol })
    return response.data
  },

  /**
   * Get all onboarding tasks
   */
  getOnboardingTasks: async () => {
    const response = await apiRoot.get('/tasks')
    return response.data
  },

  /**
   * Get a specific task status
   */
  getTaskStatus: async (taskId: string) => {
    const response = await apiRoot.get(`/tasks/${taskId}`)
    return response.data
  },

  /**
   * Update session preferences for a symbol
   */
  updateSessionPreferences: async (symbol: string, enabledSessions: string[]) => {
    const response = await apiRoot.post(`/symbols/${symbol}/sessions`, { 
      enabled_sessions: enabledSessions 
    })
    return response.data
  },

  /**
   * Get session preferences for a symbol
   */
  getSessionPreferences: async (symbol: string) => {
    const response = await apiRoot.get(`/symbols/${symbol}/sessions`)
    return response.data
  },
}
