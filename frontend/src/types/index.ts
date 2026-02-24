// SmartSpend360 — TypeScript type definitions

export interface Transaction {
  transaction_id: string
  user_id: string
  date: string
  merchant_name: string
  category: string
  amount_abs: number
  is_debit: boolean
  is_weekend?: boolean
  anomaly_score?: number
  anomaly_severity?: 'HIGH' | 'MEDIUM' | 'NORMAL'
  rolling_30d_mean?: number
  payment_channel?: string
}

export interface PageInfo {
  page: number
  page_size: number
  total_count: number
  total_pages: number
}

export interface TransactionListResponse {
  transactions: Transaction[]
  total_count: number
  page_info: PageInfo
}

export interface AnomalyRecord {
  alert_id: string
  user_id: string
  date: string
  merchant_name?: string
  category?: string
  anomaly_score: number
  severity: 'HIGH' | 'MEDIUM'
  daily_total?: number
  status: 'active' | 'acknowledged'
  anomaly_explanation?: string
  timestamp?: string
}

export interface AnomalyListResponse {
  anomalies: AnomalyRecord[]
  total_count: number
  high_count: number
  medium_count: number
}

export interface ForecastPoint {
  ds: string
  yhat: number
  yhat_lower: number
  yhat_upper: number
  yhat_lower_95?: number
  yhat_upper_95?: number
  trend?: number
  is_future: boolean
}

export interface ForecastResponse {
  user_id: string
  run_date: string
  horizon_days: number
  runway_days: number
  projected_30d_spend: number
  mean_daily_spend: number
  health_score?: number
  forecast: ForecastPoint[]
}

export interface CategorySummary {
  category: string
  amount_abs: number
  percentage: number
  mom_change?: number
}

export interface MerchantSummary {
  merchant_normalized: string
  total_spend: number
  txn_count: number
}

export interface MetricsSummaryResponse {
  user_id: string
  date: string
  burn_rate: number
  health_score: number
  anomaly_count: number
  high_anomaly_count: number
  mtd_spend: number
  last_month_spend: number
  mom_change_pct: number
  avg_daily_spend: number
  top_categories: CategorySummary[]
  top_merchants: MerchantSummary[]
  runway_days: number
  last_updated: string
}

export interface PipelineStageStatus {
  stage: string
  status: 'success' | 'failed' | 'running' | 'pending' | 'error'
  last_run_time?: string
  records_processed: number
  duration_seconds?: number
  error_count: number
  details?: string
}

export interface PipelineStatusResponse {
  stages: PipelineStageStatus[]
  overall_status: string
  last_full_run?: string
}

export interface AlertRecord {
  user_id: string
  alert_id: string
  alert_type: string
  threshold: number
  category?: string
  channel: string
  enabled: boolean
  created_at: string
  triggered_count: number
  last_triggered?: string
}

export interface AlertEvent {
  alert_id: string
  alert_type: string
  triggered_at: string
  actual_value: number
  threshold: number
  message: string
}

export interface AlertListResponse {
  alerts: AlertRecord[]
  recent_events: AlertEvent[]
}

export interface HealthResponse {
  status: string
  version: string
  uptime_seconds: number
  aws_connected: boolean
  environment: string
}
