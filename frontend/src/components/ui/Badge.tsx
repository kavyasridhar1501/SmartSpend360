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
    default: 'bg-slate-100 text-slate-700 border-slate-200',
    success: 'bg-green-50 text-green-700 border-green-200',
    warning: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    danger: 'bg-red-50 text-red-700 border-red-200',
    info: 'bg-blue-50 text-blue-700 border-blue-200',
    severity: severity ? severityColor(severity) : 'bg-slate-100 text-slate-700 border-slate-200',
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
