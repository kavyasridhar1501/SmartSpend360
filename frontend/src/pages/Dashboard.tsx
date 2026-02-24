import {
  AreaChart, Area, BarChart, Bar, Cell, PieChart, Pie, Legend,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  DollarSign, ShieldAlert, Heart, Clock, Activity,
} from 'lucide-react'
import { useMetricsSummary, useAnomalies, usePipelineStatus, useTransactions } from '@/hooks/useQueries'
import { KPICard } from '@/components/ui/KPICard'
import { KPICardSkeleton, ChartSkeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { SeverityBadge } from '@/components/ui/Badge'
import { formatCurrency, formatDate, healthScoreColor, CATEGORY_COLORS } from '@/lib/utils'
import type { Transaction, CategorySummary, AnomalyRecord } from '@/types'

function SpendChart() {
  const { data, isLoading } = useTransactions({ page_size: 200 })

  if (isLoading) return <ChartSkeleton height="h-64" />

  const dailyMap: Record<string, number> = {}
  data?.transactions?.forEach((t: Transaction) => {
    if (t.is_debit) {
      dailyMap[t.date] = (dailyMap[t.date] || 0) + t.amount_abs
    }
  })

  const chartData = Object.entries(dailyMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, amount]) => ({ date, amount: Math.round(amount * 100) / 100 }))

  const withMA = chartData.map((d, i) => {
    const window = chartData.slice(Math.max(0, i - 6), i + 1)
    const ma = window.reduce((s, x) => s + x.amount, 0) / window.length
    return { ...d, ma: Math.round(ma * 100) / 100 }
  })

  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={withMA} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <defs>
          <linearGradient id="spendGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#0d9488" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#0d9488" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false}
          tickFormatter={(v) => `$${v}`} />
        <Tooltip
          contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8 }}
          labelStyle={{ color: '#64748b' }}
          formatter={(v: number) => [formatCurrency(v), 'Spend']}
        />
        <Area type="monotone" dataKey="amount" stroke="#0d9488" fill="url(#spendGradient)"
          strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="ma" stroke="#6366f1" fill="none"
          strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="7d avg" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function CategoryDonut() {
  const { data } = useMetricsSummary()
  const categories = data?.top_categories || []
  if (!categories.length) return <ChartSkeleton height="h-48" />

  const pieData = categories.slice(0, 6).map((c: CategorySummary) => ({
    name: c.category,
    value: c.amount_abs,
  }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={pieData}
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={80}
          paddingAngle={2}
          dataKey="value"
        >
          {pieData.map((entry: { name: string; value: number }) => (
            <Cell key={entry.name} fill={CATEGORY_COLORS[entry.name] || '#94a3b8'} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8 }}
          formatter={(v: number) => [formatCurrency(v), '']}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value) => <span style={{ color: '#64748b', fontSize: 12 }}>{value}</span>}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

function WeeklyBarChart() {
  const { data } = useTransactions({ page_size: 200 })
  if (!data) return <ChartSkeleton height="h-40" />

  const weeklyMap: Record<number, number> = {}
  data.transactions?.forEach((t: Transaction) => {
    if (!t.is_debit) return
    const weekAgo = Math.floor(
      (Date.now() - new Date(t.date).getTime()) / (7 * 86400 * 1000)
    )
    if (weekAgo >= 0 && weekAgo < 4) {
      weeklyMap[weekAgo] = (weeklyMap[weekAgo] || 0) + t.amount_abs
    }
  })

  const chartData = [3, 2, 1, 0].map((w) => ({
    week: w === 0 ? 'This week' : `${w}w ago`,
    amount: Math.round((weeklyMap[w] || 0) * 100) / 100,
  }))

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={chartData} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
        <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} />
        <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false}
          tickFormatter={(v) => `$${v}`} />
        <Tooltip
          contentStyle={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8 }}
          formatter={(v: number) => [formatCurrency(v), 'Spend']}
        />
        <Bar dataKey="amount" fill="#0d9488" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

function PipelineWidget() {
  const { data } = usePipelineStatus()
  const stages = data?.stages?.slice(0, 7) || []

  return (
    <div className="flex flex-wrap gap-3">
      {stages.map((stage: { status: string }, i: number) => (
        <div key={i} className="flex items-center gap-2">
          {i > 0 && <div className="w-6 h-px bg-slate-300 hidden sm:block" />}
          <div className="flex flex-col items-center gap-1">
            <div className={`w-2.5 h-2.5 rounded-full ${
              stage.status === 'success' ? 'bg-green-500' :
              stage.status === 'running' ? 'bg-blue-500 animate-pulse' :
              stage.status === 'failed' ? 'bg-red-500' :
              'bg-slate-400'
            }`} />
            <span className="text-xs text-slate-400 whitespace-nowrap">{i + 1}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { data: metrics, isLoading: metricsLoading, error: metricsError, refetch } = useMetricsSummary()
  const { data: anomalies } = useAnomalies({})

  return (
    <div className="p-4 lg:p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Overview</h1>
        <p className="text-slate-500 text-sm mt-1">Financial analytics at a glance</p>
      </div>

      {/* KPI Cards */}
      {metricsError ? (
        <ErrorState message={metricsError.message} onRetry={() => refetch()} />
      ) : metricsLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <KPICardSkeleton key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            title="MTD Spend"
            value={metrics?.mtd_spend || 0}
            change={metrics?.mom_change_pct}
            icon={DollarSign}
          />
          <KPICard
            title="Health Score"
            value={`${metrics?.health_score || 0}/100`}
            icon={Heart}
            iconColor="text-green-600"
            valueColor={healthScoreColor(metrics?.health_score || 0)}
            description="Composite cash flow health"
          />
          <KPICard
            title="Anomalies This Month"
            value={metrics?.anomaly_count || 0}
            description={`${metrics?.high_anomaly_count || 0} HIGH severity`}
            icon={ShieldAlert}
            iconColor="text-red-500"
          />
          <KPICard
            title="Days of Runway"
            value={`${metrics?.runway_days || 0}`}
            unit="days"
            description="Based on 30-day forecast"
            icon={Clock}
            iconColor="text-teal-600"
          />
        </div>
      )}

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">
            Daily Spend — 90 Days
            <span className="ml-2 text-xs font-normal text-slate-400">with 7-day moving average</span>
          </h3>
          <SpendChart />
        </div>
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-700 mb-4">Category Breakdown</h3>
          <CategoryDonut />
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Recent Anomalies */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-700">Recent Anomalies</h3>
            <span className="text-xs text-slate-400">{anomalies?.total_count || 0} total</span>
          </div>
          <div className="space-y-3">
            {anomalies?.anomalies?.slice(0, 3).map((a: AnomalyRecord) => (
              <div key={a.alert_id} className="flex items-start justify-between p-3 bg-slate-50 rounded-lg border border-slate-100">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-800">
                      {a.merchant_name || a.category || 'Unknown'}
                    </span>
                    <SeverityBadge severity={a.severity} />
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">{formatDate(a.date)}</p>
                </div>
                {a.daily_total && (
                  <span className="text-sm font-mono text-red-600">{formatCurrency(a.daily_total)}</span>
                )}
              </div>
            ))}
            {!anomalies?.anomalies?.length && (
              <p className="text-sm text-slate-400 text-center py-4">No anomalies detected</p>
            )}
          </div>
        </div>

        {/* Pipeline + Weekly */}
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-700 mb-4">Week-over-Week Spend</h3>
            <WeeklyBarChart />
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-teal-600" />
              <h3 className="text-sm font-semibold text-slate-700">Pipeline Status</h3>
            </div>
            <PipelineWidget />
            <p className="text-xs text-slate-400 mt-3">7 stages — hover for details on Pipeline page</p>
          </div>
        </div>
      </div>
    </div>
  )
}
