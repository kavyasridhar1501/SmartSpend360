import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn, formatCurrency, formatPct } from '@/lib/utils'

interface KPICardProps {
  title: string
  value: string | number
  unit?: string
  change?: number
  changeLabel?: string
  icon?: React.ElementType
  iconColor?: string
  valueColor?: string
  description?: string
  children?: React.ReactNode
}

export function KPICard({
  title,
  value,
  unit,
  change,
  changeLabel,
  icon: Icon,
  iconColor = 'text-teal-600',
  valueColor,
  description,
  children,
}: KPICardProps) {
  const displayValue =
    typeof value === 'number'
      ? formatCurrency(value, true)
      : value

  const changePositive = change !== undefined && change > 0
  const changeNegative = change !== undefined && change < 0

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 hover:border-slate-300 transition-colors shadow-sm">
      <div className="flex items-start justify-between mb-3">
        <span className="text-sm font-medium text-slate-500">{title}</span>
        {Icon && (
          <div className={cn('p-2 rounded-lg bg-slate-100', iconColor)}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-1.5 mb-2">
        <span className={cn('text-2xl font-bold text-slate-900', valueColor)}>
          {displayValue}
        </span>
        {unit && <span className="text-sm text-slate-500">{unit}</span>}
      </div>

      {change !== undefined && (
        <div className="flex items-center gap-1.5">
          {changePositive ? (
            <TrendingUp className="w-3.5 h-3.5 text-red-500" />
          ) : changeNegative ? (
            <TrendingDown className="w-3.5 h-3.5 text-green-600" />
          ) : (
            <Minus className="w-3.5 h-3.5 text-slate-400" />
          )}
          <span
            className={cn(
              'text-xs font-medium',
              changePositive ? 'text-red-500' : changeNegative ? 'text-green-600' : 'text-slate-400',
            )}
          >
            {formatPct(change)} {changeLabel || 'vs last month'}
          </span>
        </div>
      )}

      {description && (
        <p className="text-xs text-slate-400 mt-1">{description}</p>
      )}

      {children}
    </div>
  )
}
