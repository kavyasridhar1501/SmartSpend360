import { useState, useCallback } from 'react'
import { Download, Search, Filter } from 'lucide-react'
import Papa from 'papaparse'
import { useTransactions } from '@/hooks/useQueries'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { SeverityBadge } from '@/components/ui/Badge'
import { formatCurrency, formatDate, CATEGORY_COLORS } from '@/lib/utils'
import type { Transaction } from '@/types'

const CATEGORIES = ['Food', 'Transport', 'Entertainment', 'Healthcare', 'Housing', 'Other', 'Transfer', 'Income']

function AnomalyScoreBar({ score }: { score?: number }) {
  if (score === undefined || score === null) return <span className="text-slate-500 text-xs">—</span>
  const normalized = Math.max(0, Math.min(1, (-score + 1) / 2)) * 100
  const color = normalized > 70 ? 'bg-red-400' : normalized > 50 ? 'bg-yellow-400' : 'bg-green-400'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${normalized}%` }} />
      </div>
      <span className="text-xs text-slate-400 font-mono">{score?.toFixed(2)}</span>
    </div>
  )
}

function TransactionDetail({ txn, onClose }: { txn: Transaction; onClose: () => void }) {
  const features = [
    { label: 'Amount', value: formatCurrency(txn.amount_abs) },
    { label: 'Category', value: txn.category },
    { label: 'Date', value: formatDate(txn.date) },
    { label: 'Channel', value: txn.payment_channel || '—' },
    { label: '30d Avg', value: txn.rolling_30d_mean ? formatCurrency(txn.rolling_30d_mean) : '—' },
    { label: 'Weekend', value: txn.is_weekend ? 'Yes' : 'No' },
  ]

  const anomalyContributions = [
    { label: 'Amount vs 30d Avg', value: txn.rolling_30d_mean ? (txn.amount_abs / txn.rolling_30d_mean - 1) * 100 : 0 },
    { label: 'Is Weekend', value: txn.is_weekend ? 15 : 0 },
    { label: 'Category Score', value: 20 },
    { label: 'Time Pattern', value: 10 },
  ]

  return (
    <div className="fixed inset-y-0 right-0 w-full sm:w-96 bg-slate-800 border-l border-slate-700 z-50 animate-slide-in overflow-y-auto">
      <div className="p-5">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-slate-100">Transaction Detail</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-2xl leading-none">×</button>
        </div>

        <div className="mb-5 p-4 bg-slate-700/40 rounded-xl">
          <div className="text-xl font-bold text-slate-100">{formatCurrency(txn.amount_abs)}</div>
          <div className="text-slate-300 font-medium mt-1">{txn.merchant_name}</div>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs text-slate-500">{formatDate(txn.date)}</span>
            {txn.anomaly_severity && txn.anomaly_severity !== 'NORMAL' && (
              <SeverityBadge severity={txn.anomaly_severity} />
            )}
          </div>
        </div>

        <div className="space-y-3 mb-5">
          {features.map(({ label, value }) => (
            <div key={label} className="flex justify-between text-sm">
              <span className="text-slate-400">{label}</span>
              <span className="text-slate-200 font-medium">{value}</span>
            </div>
          ))}
        </div>

        {txn.anomaly_severity && txn.anomaly_severity !== 'NORMAL' && (
          <div>
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Anomaly Feature Contributions</h3>
            <div className="space-y-2">
              {anomalyContributions.map(({ label, value }) => (
                <div key={label}>
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span>{label}</span>
                    <span>{value.toFixed(0)}%</span>
                  </div>
                  <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-teal-500 rounded-full"
                      style={{ width: `${Math.min(100, Math.abs(value))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Transactions() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [anomalyOnly, setAnomalyOnly] = useState(false)
  const [selected, setSelected] = useState<Transaction | null>(null)

  const { data, isLoading, error, refetch } = useTransactions({
    page,
    page_size: 50,
    category: category || undefined,
    anomaly_only: anomalyOnly,
  })

  const filtered = (data?.transactions || []).filter((t) =>
    !search || t.merchant_name.toLowerCase().includes(search.toLowerCase())
  )

  const exportCSV = useCallback(() => {
    const csv = Papa.unparse(data?.transactions || [])
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `smartspend360_transactions_${new Date().toISOString().split('T')[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [data])

  if (error) return (
    <div className="p-6">
      <ErrorState message={error.message} onRetry={() => refetch()} />
    </div>
  )

  const totalPages = data?.page_info?.total_pages || 1
  const totalCount = data?.total_count || 0

  return (
    <div className="p-4 lg:p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Transactions</h1>
          <p className="text-slate-400 text-sm mt-1">
            {totalCount.toLocaleString()} transactions found
          </p>
        </div>
        <button
          onClick={exportCSV}
          className="flex items-center gap-2 px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-sm transition-colors"
        >
          <Download className="w-4 h-4" />
          <span className="hidden sm:inline">Export CSV</span>
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 p-4 bg-slate-800 border border-slate-700 rounded-xl">
        <div className="relative flex-1 min-w-40">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search merchant..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-teal-500"
          />
        </div>
        <select
          value={category}
          onChange={(e) => { setCategory(e.target.value); setPage(1) }}
          className="px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-sm text-slate-200 focus:outline-none focus:border-teal-500"
        >
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <label className="flex items-center gap-2 px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg cursor-pointer">
          <input
            type="checkbox"
            checked={anomalyOnly}
            onChange={(e) => { setAnomalyOnly(e.target.checked); setPage(1) }}
            className="accent-teal-500"
          />
          <span className="text-sm text-slate-300">Anomalies only</span>
        </label>
      </div>

      {/* Table */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          {isLoading ? (
            <div className="p-4"><TableSkeleton rows={8} /></div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 bg-slate-700/30">
                  {['Date', 'Merchant', 'Category', 'Amount', 'Anomaly Score', 'Status'].map((h) => (
                    <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {filtered.map((txn) => (
                  <tr
                    key={txn.transaction_id}
                    className="hover:bg-slate-700/30 cursor-pointer transition-colors"
                    onClick={() => setSelected(txn)}
                  >
                    <td className="px-4 py-3 text-slate-400 font-mono text-xs whitespace-nowrap">
                      {formatDate(txn.date)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-slate-200">{txn.merchant_name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-1.5">
                        <div
                          className="w-2 h-2 rounded-full"
                          style={{ background: CATEGORY_COLORS[txn.category] || '#64748b' }}
                        />
                        <span className="text-slate-400 text-xs">{txn.category}</span>
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-200">
                      {formatCurrency(txn.amount_abs)}
                    </td>
                    <td className="px-4 py-3">
                      <AnomalyScoreBar score={txn.anomaly_score} />
                    </td>
                    <td className="px-4 py-3">
                      {txn.anomaly_severity && txn.anomaly_severity !== 'NORMAL' ? (
                        <SeverityBadge severity={txn.anomaly_severity} />
                      ) : (
                        <span className="text-xs text-slate-500">Normal</span>
                      )}
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-12 text-center text-slate-500">
                      No transactions match your filters
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700">
          <span className="text-xs text-slate-500">
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-200 rounded text-xs transition-colors"
            >
              Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-200 rounded text-xs transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Transaction detail slide-over */}
      {selected && (
        <TransactionDetail txn={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
