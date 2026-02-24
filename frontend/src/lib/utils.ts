import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(amount: number, compact = false): string {
  if (compact && Math.abs(amount) >= 1000) {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(amount)
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('en-US').format(n)
}

export function formatPct(n: number, decimals = 1): string {
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(decimals)}%`
}

export function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatTime(isoStr: string): string {
  if (!isoStr) return ''
  return new Date(isoStr).toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function severityColor(severity: string): string {
  switch (severity) {
    case 'HIGH':
      return 'text-red-700 bg-red-50 border-red-200'
    case 'MEDIUM':
      return 'text-yellow-700 bg-yellow-50 border-yellow-200'
    default:
      return 'text-slate-600 bg-slate-100 border-slate-200'
  }
}

export function healthScoreColor(score: number): string {
  if (score >= 70) return 'text-green-600'
  if (score >= 40) return 'text-yellow-700'
  return 'text-red-600'
}

export function statusColor(status: string): string {
  switch (status?.toLowerCase()) {
    case 'success':
      return 'text-green-600'
    case 'running':
      return 'text-blue-600'
    case 'failed':
    case 'error':
      return 'text-red-600'
    default:
      return 'text-slate-500'
  }
}

export const CATEGORY_COLORS: Record<string, string> = {
  Housing: '#6366f1',
  Food: '#14b8a6',
  Transport: '#f59e0b',
  Entertainment: '#ec4899',
  Healthcare: '#10b981',
  Other: '#8b5cf6',
  Income: '#22c55e',
  Transfer: '#64748b',
}
