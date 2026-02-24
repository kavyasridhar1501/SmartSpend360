import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { AlertTriangle, CheckCircle2, ChevronDown } from 'lucide-react'
import { useAnomalies, useAcknowledgeAnomaly } from '@/hooks/useQueries'
import { SeverityBadge } from '@/components/ui/Badge'
import { ErrorState } from '@/components/ui/ErrorState'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatCurrency, formatDate } from '@/lib/utils'
import type { AnomalyRecord } from '@/types'

type SeverityFilter = 'ALL' | 'HIGH' | 'MEDIUM'

function AnomalyCard({ anomaly }: { anomaly: AnomalyRecord }) {
  const [expanded, setExpanded] = useState(false)
  const acknowledge = useAcknowledgeAnomaly()

  const isHigh = anomaly.severity === 'HIGH'
  const isAcknowledged = anomaly.status === 'acknowledged'

  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        isAcknowledged
          ? 'border-slate-600/50 opacity-60'
          : isHigh
          ? 'border-red-500/30 bg-red-500/5'
          : 'border-yellow-500/30 bg-yellow-500/5'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-slate-100 text-sm">
              {anomaly.merchant_name || anomaly.category || 'Anomaly Detected'}
            </span>
            <SeverityBadge severity={anomaly.severity} />
            {isAcknowledged && (
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                Acknowledged
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-xs text-slate-400">{formatDate(anomaly.date)}</span>
            {anomaly.category && (
              <span className="text-xs text-slate-500">{anomaly.category}</span>
            )}
          </div>
          {anomaly.anomaly_explanation && (
            <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
              {anomaly.anomaly_explanation}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2 flex-shrink-0">
          {anomaly.daily_total && (
            <span className={`font-mono font-semibold text-sm ${isHigh ? 'text-red-400' : 'text-yellow-400'}`}>
              {formatCurrency(anomaly.daily_total)}
            </span>
          )}
          <span className="text-xs text-slate-500 font-mono">
            score: {anomaly.anomaly_score.toFixed(2)}
          </span>
        </div>
      </div>

      {!isAcknowledged && (
        <div className="flex gap-2 mt-3 pt-3 border-t border-slate-700/50">
          <button
            onClick={() => acknowledge.mutate({ anomalyId: anomaly.alert_id, note: '' })}
            disabled={acknowledge.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-xs transition-colors disabled:opacity-50"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            Acknowledge
          </button>
        </div>
      )}
    </div>
  )
}

function AnomalyFrequencyChart({ anomalies }: { anomalies: AnomalyRecord[] }) {
  const daily: Record<string, number> = {}
  anomalies.forEach((a) => {
    daily[a.date] = (daily[a.date] || 0) + 1
  })
  const data = Object.entries(daily)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-30)
    .map(([date, count]) => ({ date, count }))

  if (!data.length) return null

  return (
    <ResponsiveContainer width="100%" height={120}>
      <BarChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip
          contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
          labelStyle={{ color: '#94a3b8' }}
        />
        <Bar dataKey="count" fill="#ef4444" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function Anomalies() {
  const [severity, setSeverity] = useState<SeverityFilter>('ALL')
  const { data, isLoading, error, refetch } = useAnomalies({ severity })

  // Group by date
  const grouped: Record<string, AnomalyRecord[]> = {}
  data?.anomalies?.forEach((a: AnomalyRecord) => {
    grouped[a.date] = grouped[a.date] || []
    grouped[a.date].push(a)
  })
  const sortedDates = Object.keys(grouped).sort((a, b) => b.localeCompare(a))

  return (
    <div className="p-4 lg:p-6 max-w-5xl mx-auto space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Anomalies</h1>
        <p className="text-slate-400 text-sm mt-1">
          {data?.total_count || 0} detected —{' '}
          <span className="text-red-400">{data?.high_count || 0} HIGH</span>,{' '}
          <span className="text-yellow-400">{data?.medium_count || 0} MEDIUM</span>
        </p>
      </div>

      {/* Frequency chart */}
      {data?.anomalies && (
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Anomaly Frequency — Last 30 Days</h3>
          <AnomalyFrequencyChart anomalies={data.anomalies} />
        </div>
      )}

      {/* Severity tabs */}
      <div className="flex gap-1 p-1 bg-slate-800 border border-slate-700 rounded-lg w-fit">
        {(['ALL', 'HIGH', 'MEDIUM'] as SeverityFilter[]).map((s) => (
          <button
            key={s}
            onClick={() => setSeverity(s)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              severity === s
                ? 'bg-teal-500/20 text-teal-300 border border-teal-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {/* List */}
      {error ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      ) : sortedDates.length === 0 ? (
        <div className="text-center py-16">
          <CheckCircle2 className="w-12 h-12 text-green-400 mx-auto mb-3" />
          <h3 className="text-lg font-semibold text-slate-200">No anomalies found</h3>
          <p className="text-slate-400 text-sm mt-1">
            {severity !== 'ALL' ? `No ${severity} severity anomalies` : 'Spending patterns look normal'}
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {sortedDates.map((date) => (
            <div key={date}>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
                {formatDate(date)}
              </h3>
              <div className="space-y-3">
                {grouped[date].map((a) => (
                  <AnomalyCard key={a.alert_id} anomaly={a} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
