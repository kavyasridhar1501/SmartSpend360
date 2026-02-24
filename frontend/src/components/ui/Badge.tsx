import { cn, severityColor } from '@/lib/utils'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'severity'
  severity?: string
  className?: string
}

export function Badge({ children, variant = 'default', severity, className }: BadgeProps) {
  const base = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border'

  const variants = {
    default: 'bg-slate-700 text-slate-300 border-slate-600',
    success: 'bg-green-500/10 text-green-400 border-green-500/20',
    warning: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    danger: 'bg-red-500/10 text-red-400 border-red-500/20',
    info: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    severity: severity ? severityColor(severity) : 'bg-slate-700 text-slate-300 border-slate-600',
  }

  return (
    <span className={cn(base, variants[variant], className)}>
      {children}
    </span>
  )
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <Badge variant="severity" severity={severity}>
      {severity}
    </Badge>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const variant =
    status === 'success' ? 'success' :
    status === 'running' ? 'info' :
    status === 'failed' || status === 'error' ? 'danger' :
    'default'

  return <Badge variant={variant}>{status}</Badge>
}
