import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import {
  LayoutDashboard,
  List,
  AlertTriangle,
  TrendingUp,
  Bell,
  Activity,
  ChevronLeft,
  ChevronRight,
  Menu,
  X,
  Zap,
} from 'lucide-react'
import { cn, formatDate } from '@/lib/utils'
import { useHealth, usePipelineStatus } from '@/hooks/useQueries'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/transactions', label: 'Transactions', icon: List },
  { to: '/anomalies', label: 'Anomalies', icon: AlertTriangle },
  { to: '/forecast', label: 'Forecast', icon: TrendingUp },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/pipeline', label: 'Pipeline', icon: Activity },
]

function PipelineStatusDot() {
  const { data } = usePipelineStatus()
  const status = data?.overall_status
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={cn(
          'w-2 h-2 rounded-full',
          status === 'success' ? 'bg-green-500 animate-pulse-slow' :
          status === 'partial' ? 'bg-yellow-500' :
          'bg-slate-400',
        )}
      />
      <span className="text-xs text-slate-500">
        {status === 'success' ? 'Live' : status === 'partial' ? 'Partial' : 'Stale'}
      </span>
    </div>
  )
}

export default function Layout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { data: health } = useHealth()

  const now = new Date()

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed lg:static inset-y-0 left-0 z-50 flex flex-col bg-white border-r border-slate-200 transition-all duration-300',
          collapsed ? 'w-16' : 'w-60',
          mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        )}
      >
        {/* Logo */}
        <div className="flex items-center h-16 px-4 border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="p-1.5 bg-teal-50 rounded-lg flex-shrink-0">
              <Zap className="w-5 h-5 text-teal-600" />
            </div>
            {!collapsed && (
              <span className="font-bold text-sm text-slate-900 whitespace-nowrap">
                SmartSpend360
              </span>
            )}
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                  isActive
                    ? 'bg-teal-50 text-teal-700 border border-teal-200'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100',
                  collapsed && 'justify-center',
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {!collapsed && <span className="whitespace-nowrap">{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Collapse toggle (desktop) */}
        <div className="hidden lg:flex items-center justify-end px-3 py-3 border-t border-slate-200">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100"
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between h-16 px-4 lg:px-6 bg-white border-b border-slate-200 flex-shrink-0">
          <button
            className="lg:hidden p-2 text-slate-500 hover:text-slate-800"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>

          <div className="flex items-center gap-4 ml-auto">
            <PipelineStatusDot />
            <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-400">
              <span>Updated:</span>
              <span className="text-slate-500">
                {now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            {health && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-100 rounded-full">
                <div className={cn('w-1.5 h-1.5 rounded-full', health.aws_connected ? 'bg-green-500' : 'bg-slate-400')} />
                <span className="text-xs text-slate-500">v{health.version}</span>
              </div>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
