import { useState } from 'react'
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import { TrendingUp, Clock, DollarSign, Target, Sliders } from 'lucide-react'
import { useForecast } from '@/hooks/useQueries'
import { ChartSkeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { formatCurrency, formatDate, healthScoreColor } from '@/lib/utils'
import type { ForecastPoint } from '@/types'

function ForecastChart({ data }: { data: ReturnType<typeof useForecast>['data'] }) {
  if (!data) return <ChartSkeleton height="h-80" />
  const today = new Date().toISOString().split('T')[0]

  const chartData = data.forecast.map((p: ForecastPoint) => ({
    ...p,
    ds_label: p.ds.slice(5), // MM-DD
    historical_yhat: !p.is_future ? p.yhat : undefined,
    forecast_yhat: p.is_future ? p.yhat : undefined,
    band_80_lower: p.yhat_lower,
    band_80_upper: p.yhat_upper,
    band_95_lower: p.yhat_lower_95 ?? p.yhat_lower * 0.9,
    band_95_upper: p.yhat_upper_95 ?? p.yhat_upper * 1.1,
  }))

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
        <defs>
          <linearGradient id="band95" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.08} />
            <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="band80" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.18} />
            <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.06} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="ds_label" tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false}
          interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickLine={false} axisLine={false}
          tickFormatter={(v) => `$${v}`} />
        <Tooltip
          contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
          formatter={(v: number, name: string) => [
            typeof v === 'number' ? formatCurrency(v) : v,
            name,
          ]}
        />
        <Legend formatter={(v) => <span style={{ color: '#94a3b8', fontSize: 11 }}>{v}</span>} />

        {/* 95% band */}
        <Area type="monotone" dataKey="band_95_upper" stroke="none" fill="url(#band95)" name="95% CI upper" legendType="none" />
        <Area type="monotone" dataKey="band_95_lower" stroke="none" fill="#0f172a" name="95% CI lower" legendType="none" />

        {/* 80% band */}
        <Area type="monotone" dataKey="band_80_upper" stroke="none" fill="url(#band80)" name="80% CI" />
        <Area type="monotone" dataKey="band_80_lower" stroke="none" fill="#0f172a" legendType="none" />

        {/* Historical line */}
        <Line type="monotone" dataKey="historical_yhat" stroke="#14b8a6" strokeWidth={2}
          dot={false} name="Historical" connectNulls={false} />

        {/* Forecast line */}
        <Line type="monotone" dataKey="forecast_yhat" stroke="#14b8a6" strokeWidth={2}
          strokeDasharray="6 3" dot={false} name="Forecast" connectNulls={false} />

        {/* Today marker */}
        <ReferenceLine x={today.slice(5)} stroke="#6366f1" strokeDasharray="4 2"
          label={{ value: 'Today', position: 'top', fill: '#6366f1', fontSize: 11 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

function WhatIfSimulator({ baseRunway, baseSpend }: { baseRunway: number; baseSpend: number }) {
  const [income, setIncome] = useState(6000)
  const [reduction, setReduction] = useState(0)

  const adjustedMonthlySpend = baseSpend * (1 - reduction / 100)
  const dailySpend = adjustedMonthlySpend / 30
  const dailyIncome = income / 30
  const netDaily = dailyIncome - dailySpend
  const runway = netDaily > 0 ? Infinity : Math.abs(income / netDaily)
  const projectedSavings = (dailyIncome - dailySpend) * 30

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <Sliders className="w-4 h-4 text-teal-400" />
        <h3 className="text-sm font-semibold text-slate-200">What-If Simulator</h3>
      </div>

      <div className="space-y-5">
        <div>
          <div className="flex justify-between text-sm mb-2">
            <label className="text-slate-300">Monthly Income Assumption</label>
            <span className="font-mono text-teal-400">{formatCurrency(income)}</span>
          </div>
          <input
            type="range" min={0} max={20000} step={500} value={income}
            onChange={(e) => setIncome(+e.target.value)}
            className="w-full accent-teal-500"
          />
          <div className="flex justify-between text-xs text-slate-500 mt-1">
            <span>$0</span><span>$20,000</span>
          </div>
        </div>

        <div>
          <div className="flex justify-between text-sm mb-2">
            <label className="text-slate-300">Discretionary Spend Reduction</label>
            <span className="font-mono text-teal-400">{reduction}%</span>
          </div>
          <input
            type="range" min={0} max={50} step={5} value={reduction}
            onChange={(e) => setReduction(+e.target.value)}
            className="w-full accent-teal-500"
          />
          <div className="flex justify-between text-xs text-slate-500 mt-1">
            <span>0%</span><span>50%</span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 pt-3 border-t border-slate-700">
          <div className="text-center p-3 bg-slate-700/40 rounded-lg">
            <div className="text-xs text-slate-400 mb-1">Adjusted Runway</div>
            <div className={`text-xl font-bold ${runway === Infinity ? 'text-green-400' : runway > 30 ? 'text-teal-400' : 'text-red-400'}`}>
              {runway === Infinity ? '∞' : `${Math.round(runway)}d`}
            </div>
          </div>
          <div className="text-center p-3 bg-slate-700/40 rounded-lg">
            <div className="text-xs text-slate-400 mb-1">Projected Savings</div>
            <div className={`text-xl font-bold ${projectedSavings >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {projectedSavings >= 0 ? '+' : ''}{formatCurrency(projectedSavings, true)}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Forecast() {
  const [horizon, setHorizon] = useState(30)
  const { data, isLoading, error, refetch } = useForecast(horizon)

  if (error) return (
    <div className="p-6">
      <ErrorState message={error.message} onRetry={() => refetch()} />
    </div>
  )

  const summaryCards = [
    {
      title: 'Projected 30-Day Spend',
      value: data ? formatCurrency(data.projected_30d_spend) : '—',
      icon: DollarSign,
      color: 'text-teal-400',
    },
    {
      title: 'Estimated Runway',
      value: data ? `${data.runway_days} days` : '—',
      icon: Clock,
      color: data?.runway_days && data.runway_days < 30 ? 'text-red-400' : 'text-green-400',
    },
    {
      title: 'Mean Daily Spend',
      value: data ? formatCurrency(data.mean_daily_spend) : '—',
      icon: TrendingUp,
      color: 'text-slate-300',
    },
    {
      title: 'Health Score',
      value: data?.health_score ? `${data.health_score}/100` : '—',
      icon: Target,
      color: healthScoreColor(data?.health_score || 0),
    },
  ]

  return (
    <div className="p-4 lg:p-6 max-w-6xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Cash Flow Forecast</h1>
          <p className="text-slate-400 text-sm mt-1">Prophet ML model — 90-day training, {horizon}-day horizon</p>
        </div>
        <select
          value={horizon}
          onChange={(e) => setHorizon(+e.target.value)}
          className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-teal-500"
        >
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={30}>30 days</option>
          <option value={60}>60 days</option>
          <option value={90}>90 days</option>
        </select>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {summaryCards.map(({ title, value, icon: Icon, color }) => (
          <div key={title} className="bg-slate-800 border border-slate-700 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon className={`w-4 h-4 ${color}`} />
              <span className="text-xs text-slate-400">{title}</span>
            </div>
            <div className={`text-xl font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>

      {/* Forecast chart */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-slate-200 mb-4">
          Forecast Chart
          <span className="ml-2 text-xs font-normal text-slate-500">
            Solid = historical · Dashed = forecast · Shaded = 80%/95% confidence
          </span>
        </h3>
        {isLoading ? <ChartSkeleton height="h-80" /> : <ForecastChart data={data} />}
      </div>

      {/* What-if simulator */}
      <WhatIfSimulator
        baseRunway={data?.runway_days || 30}
        baseSpend={data?.projected_30d_spend || 3000}
      />
    </div>
  )
}
