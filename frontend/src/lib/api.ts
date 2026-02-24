import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''
const API_KEY = import.meta.env.VITE_API_KEY || 'dev-secret-key-change-in-production'

export const apiClient = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'X-API-Key': API_KEY,
    'Content-Type': 'application/json',
  },
  timeout: 30_000,
})

// Request interceptor
apiClient.interceptors.request.use((config) => {
  return config
})

// Response interceptor for error normalization
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'An unexpected error occurred'
    return Promise.reject(new Error(message))
  },
)

// Typed API functions
export const api = {
  // Transactions
  getTransactions: (params: Record<string, unknown>) =>
    apiClient.get('/transactions', { params }).then((r) => r.data),

  // Anomalies
  getAnomalies: (params: Record<string, unknown>) =>
    apiClient.get('/anomalies', { params }).then((r) => r.data),

  acknowledgeAnomaly: (anomalyId: string, body: { user_id: string; note: string }) =>
    apiClient.post(`/anomalies/${anomalyId}/acknowledge`, body).then((r) => r.data),

  // Forecast
  getForecast: (params: Record<string, unknown>) =>
    apiClient.get('/forecast', { params }).then((r) => r.data),

  // Metrics
  getMetricsSummary: (params: Record<string, unknown>) =>
    apiClient.get('/metrics/summary', { params }).then((r) => r.data),

  // Pipeline
  getPipelineStatus: () =>
    axios.get(`${API_URL}/api/v1/pipeline/status`).then((r) => r.data),

  triggerPipeline: () =>
    apiClient.post('/pipeline/trigger').then((r) => r.data),

  // Alerts
  getAlerts: (userId: string) =>
    apiClient.get(`/alerts/${userId}`).then((r) => r.data),

  createAlert: (body: Record<string, unknown>) =>
    apiClient.post('/alerts', body).then((r) => r.data),

  // Health
  getHealth: () =>
    axios.get(`${API_URL}/health`).then((r) => r.data),
}
