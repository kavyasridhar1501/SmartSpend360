import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

const DEFAULT_USER = 'demo_user'

// ---- Transactions ----
export function useTransactions(params: {
  user_id?: string
  start_date?: string
  end_date?: string
  category?: string
  anomaly_only?: boolean
  page?: number
  page_size?: number
}) {
  return useQuery({
    queryKey: ['transactions', params],
    queryFn: () => api.getTransactions({ user_id: DEFAULT_USER, ...params }),
    staleTime: 5 * 60 * 1000,
  })
}

// ---- Anomalies ----
export function useAnomalies(params: {
  user_id?: string
  severity?: string
  start_date?: string
  end_date?: string
}) {
  return useQuery({
    queryKey: ['anomalies', params],
    queryFn: () => api.getAnomalies({ user_id: DEFAULT_USER, ...params }),
    staleTime: 5 * 60 * 1000,
  })
}

export function useAcknowledgeAnomaly() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ anomalyId, note }: { anomalyId: string; note: string }) =>
      api.acknowledgeAnomaly(anomalyId, { user_id: DEFAULT_USER, note }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['anomalies'] })
    },
  })
}

// ---- Forecast ----
export function useForecast(horizonDays = 30) {
  return useQuery({
    queryKey: ['forecast', horizonDays],
    queryFn: () => api.getForecast({ user_id: DEFAULT_USER, horizon_days: horizonDays }),
    staleTime: 30 * 60 * 1000, // 30 min — forecast changes infrequently
  })
}

// ---- Metrics ----
export function useMetricsSummary() {
  return useQuery({
    queryKey: ['metrics'],
    queryFn: () => api.getMetricsSummary({ user_id: DEFAULT_USER }),
    staleTime: 5 * 60 * 1000,
  })
}

// ---- Pipeline ----
export function usePipelineStatus() {
  return useQuery({
    queryKey: ['pipeline'],
    queryFn: () => api.getPipelineStatus(),
    refetchInterval: 30 * 1000, // Live refresh every 30s
    staleTime: 15 * 1000,
  })
}

export function useTriggerPipeline() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.triggerPipeline(),
    onSuccess: () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['pipeline'] })
      }, 3000)
    },
  })
}

// ---- Alerts ----
export function useAlerts() {
  return useQuery({
    queryKey: ['alerts', DEFAULT_USER],
    queryFn: () => api.getAlerts(DEFAULT_USER),
    staleTime: 5 * 60 * 1000,
  })
}

export function useCreateAlert() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.createAlert({ user_id: DEFAULT_USER, ...body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

// ---- Health ----
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => api.getHealth(),
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  })
}
