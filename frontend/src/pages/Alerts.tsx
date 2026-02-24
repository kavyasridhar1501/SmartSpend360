import { useState } from 'react'
import { Bell, Plus, Mail, Monitor, Trash2, Clock } from 'lucide-react'
import { useAlerts, useCreateAlert } from '@/hooks/useQueries'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/ErrorState'
import { Badge } from '@/components/ui/Badge'
import { formatCurrency, formatDate } from '@/lib/utils'
import type { AlertRecord, AlertEvent } from '@/types'

const ALERT_TYPES = [
  { value: 'daily_spend', label: 'Daily Spend Limit' },
  { value: 'single_transaction', label: 'Single Transaction' },
  { value: 'category_budget', label: 'Category Budget' },
]

const CATEGORIES = ['Food', 'Transport', 'Entertainment', 'Healthcare', 'Housing', 'Other']

function CreateAlertModal({ onClose }: { onClose: () => void }) {
  const create = useCreateAlert()
  const [form, setForm] = useState({
    alert_type: 'daily_spend',
    threshold: '',
    category: '',
    channel: 'dashboard',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await create.mutateAsync({
      alert_type: form.alert_type,
      threshold: parseFloat(form.threshold),
      category: form.category || undefined,
      channel: form.channel,
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-md p-6 animate-fade-in shadow-xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-slate-900">Create Alert</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-2xl leading-none">×</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-slate-600 mb-1.5">Alert Type</label>
            <select
              value={form.alert_type}
              onChange={(e) => setForm({ ...form, alert_type: e.target.value })}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:border-teal-500"
            >
              {ALERT_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1.5">Threshold ($)</label>
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={form.threshold}
              onChange={(e) => setForm({ ...form, threshold: e.target.value })}
              placeholder="e.g. 200.00"
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:border-teal-500"
            />
          </div>

          {form.alert_type === 'category_budget' && (
            <div>
              <label className="block text-sm text-slate-600 mb-1.5">Category</label>
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 focus:outline-none focus:border-teal-500"
              >
                <option value="">Select category</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          )}

          <div>
            <label className="block text-sm text-slate-600 mb-1.5">Notification Channel</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setForm({ ...form, channel: 'dashboard' })}
                className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors ${
                  form.channel === 'dashboard'
                    ? 'border-teal-500 bg-teal-50 text-teal-700'
                    : 'border-slate-200 bg-white text-slate-500 hover:bg-slate-50'
                }`}
              >
                <Monitor className="w-4 h-4" /> Dashboard
              </button>
              <div className="relative">
                <button
                  type="button"
                  disabled
                  className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-400 text-sm cursor-not-allowed"
                >
                  <Mail className="w-4 h-4" /> Email
                </button>
                <span className="absolute -top-2 -right-2 text-xs bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded-full">
                  Soon
                </span>
              </div>
            </div>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 border border-slate-200 text-slate-600 rounded-lg text-sm hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={create.isPending}
              className="flex-1 py-2.5 bg-teal-500 hover:bg-teal-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            >
              {create.isPending ? 'Creating...' : 'Create Alert'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function AlertCard({ alert }: { alert: AlertRecord }) {
  return (
    <div className={`bg-white border rounded-xl p-4 shadow-sm ${alert.enabled ? 'border-slate-200' : 'border-slate-200 opacity-60'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Bell className={`w-4 h-4 ${alert.enabled ? 'text-teal-600' : 'text-slate-400'}`} />
            <span className="font-medium text-sm text-slate-800">
              {ALERT_TYPES.find((t) => t.value === alert.alert_type)?.label || alert.alert_type}
            </span>
            {alert.category && <Badge variant="default">{alert.category}</Badge>}
            {!alert.enabled && <Badge variant="default">Disabled</Badge>}
          </div>
          <div className="text-sm text-teal-600 font-mono mb-2">
            Threshold: {formatCurrency(alert.threshold)}
          </div>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span className="flex items-center gap-1">
              <Monitor className="w-3 h-3" /> {alert.channel}
            </span>
            <span>Triggered: {alert.triggered_count}×</span>
            {alert.last_triggered && (
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Last: {formatDate(alert.last_triggered)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <div className={`w-2 h-2 rounded-full ${alert.enabled ? 'bg-green-500' : 'bg-slate-300'}`} />
        </div>
      </div>
    </div>
  )
}

function AlertEventRow({ event }: { event: AlertEvent }) {
  return (
    <tr className="border-b border-slate-100">
      <td className="px-4 py-2.5 text-xs text-slate-500 font-mono whitespace-nowrap">
        {formatDate(event.triggered_at)}
      </td>
      <td className="px-4 py-2.5 text-sm text-slate-700">
        {ALERT_TYPES.find((t) => t.value === event.alert_type)?.label || event.alert_type}
      </td>
      <td className="px-4 py-2.5 text-sm font-mono text-red-600">
        {formatCurrency(event.actual_value)}
      </td>
      <td className="px-4 py-2.5 text-sm text-slate-500">{formatCurrency(event.threshold)}</td>
      <td className="px-4 py-2.5 text-xs text-slate-400">{event.message}</td>
    </tr>
  )
}

export default function Alerts() {
  const [showModal, setShowModal] = useState(false)
  const { data, isLoading, error, refetch } = useAlerts()

  return (
    <div className="p-4 lg:p-6 max-w-5xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Alerts</h1>
          <p className="text-slate-500 text-sm mt-1">Spending rules and notification history</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Alert
        </button>
      </div>

      {error ? (
        <ErrorState message={error.message} onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <>
          {/* Alert cards */}
          <div>
            <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Configured Rules ({data?.alerts?.length || 0})
            </h2>
            {data?.alerts?.length ? (
              <div className="space-y-3">
                {data.alerts.map((a: AlertRecord) => <AlertCard key={a.alert_id} alert={a} />)}
              </div>
            ) : (
              <div className="text-center py-10 text-slate-400">
                <Bell className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p>No alert rules configured</p>
              </div>
            )}
          </div>

          {/* Alert history */}
          {data?.recent_events && data.recent_events.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider mb-3">
                Recent Events
              </h2>
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50">
                        {['Time', 'Type', 'Actual', 'Threshold', 'Message'].map((h) => (
                          <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_events.slice(0, 20).map((e: AlertEvent, i: number) => (
                        <AlertEventRow key={i} event={e} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {showModal && <CreateAlertModal onClose={() => setShowModal(false)} />}
    </div>
  )
}
