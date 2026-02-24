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
  iconColor = 'text-teal-400',
  valueColor,
  description,
  children,
}: KPICardProps) {
  const isCurrency = typeof value === 'number'
  const displayValue =
    typeof value === 'number'
      ? formatCurrency(value, true)
      : value

  const changePositive = change !== undefined && change > 0
  const changeNegative = change !== undefined && change < 0

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 hover:border-slate-600 transition-colors">
      <div className="flex items-start justify-between mb-3">
        <span className="text-sm font-medium text-slate-400">{title}</span>
        {Icon && (
          <div className={cn('p-2 rounded-lg bg-slate-700/50', iconColor)}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-1.5 mb-2">
        <span className={cn('text-2xl font-bold text-slate-100', valueColor)}>
          {displayValue}
        </span>
        {unit && <span className="text-sm text-slate-400">{unit}</span>}
      </div>

      {change !== undefined && (
        <div className="flex items-center gap-1.5">
          {changePositive ? (
            <TrendingUp className="w-3.5 h-3.5 text-red-400" />
          ) : changeNegative ? (
            <TrendingDown className="w-3.5 h-3.5 text-green-400" />
          ) : (
            <Minus className="w-3.5 h-3.5 text-slate-400" />
          )}
          <span
            className={cn(
              'text-xs font-medium',
              changePositive ? 'text-red-400' : changeNegative ? 'text-green-400' : 'text-slate-400',
            )}
          >
            {formatPct(change)} {changeLabel || 'vs last month'}
          </span>
        </div>
      )}

      {description && (
        <p className="text-xs text-slate-500 mt-1">{description}</p>
      )}

      {children}
    </div>
  )
}
