import { useState } from 'react'
import {
  CheckCircle2, XCircle, Loader2, Circle, RefreshCw, Play,
  ArrowRight, Database, Cpu, BarChart2, Server, Globe, BrainCircuit,
} from 'lucide-react'
import { usePipelineStatus, useTriggerPipeline } from '@/hooks/useQueries'
import { StatusBadge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { formatDate } from '@/lib/utils'
import type { PipelineStageStatus } from '@/types'

const STAGE_ICONS = [Globe, Database, Cpu, BrainCircuit, Server, BarChart2, Globe]
const STAGE_DESCRIPTIONS = [
  'Airflow fetches from Plaid, Alpha Vantage & Open Exchange Rates every 15 min',
  'Raw JSON stored in S3 Bronze layer with partitioned folder structure',
  'Databricks PySpark notebooks transform silver to gold Delta tables',
  'dbt Core builds semantic models in Athena for business-ready queries',
  'FastAPI backend serves data with auth, pagination, and caching',
  'Athena serverless SQL queries on S3 Parquet / Delta files',
  'React frontend + DynamoDB for alerts and user-specific data',
]

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'success': return <CheckCircle2 className="w-5 h-5 text-green-400" />
    case 'running': return <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
    case 'failed':
    case 'error': return <XCircle className="w-5 h-5 text-red-400" />
    default: return <Circle className="w-5 h-5 text-slate-500" />
  }
}

function PipelineStageCard({ stage, index }: { stage: PipelineStageStatus; index: number }) {
  const Icon = STAGE_ICONS[index] || Database
  const desc = STAGE_DESCRIPTIONS[index] || ''
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`bg-slate-800 border rounded-xl p-4 transition-colors cursor-pointer ${
      stage.status === 'failed' ? 'border-red-500/40' :
      stage.status === 'success' ? 'border-slate-700 hover:border-teal-500/30' :
      'border-slate-700'
    }`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">
          <StatusIcon status={stage.status} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold text-slate-500 w-5">{index + 1}.</span>
            <Icon className="w-4 h-4 text-slate-400" />
            <span className="font-semibold text-sm text-slate-200">{stage.stage}</span>
            <StatusBadge status={stage.status} />
          </div>
          <p className="text-xs text-slate-500 mt-1 ml-7 line-clamp-2">{desc}</p>
          {expanded && (
            <div className="mt-3 ml-7 grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div>
                <div className="text-xs text-slate-500 mb-0.5">Last Run</div>
                <div className="text-xs text-slate-300 font-mono">
                  {stage.last_run_time ? formatDate(stage.last_run_time) : '—'}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-0.5">Records</div>
                <div className="text-xs text-slate-300 font-mono">
                  {stage.records_processed?.toLocaleString() || '—'}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-0.5">Duration</div>
                <div className="text-xs text-slate-300 font-mono">
                  {stage.duration_seconds ? `${stage.duration_seconds}s` : '—'}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 mb-0.5">Errors</div>
                <div className={`text-xs font-mono ${stage.error_count > 0 ? 'text-red-400' : 'text-slate-300'}`}>
                  {stage.error_count}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function PipelineDiagram({ stages }: { stages: PipelineStageStatus[] }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
      <h3 className="text-sm font-semibold text-slate-200 mb-4">Pipeline Architecture</h3>
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {stages.map((stage, i) => (
          <div key={i} className="flex items-center gap-2 flex-shrink-0">
            <div className={`flex flex-col items-center p-3 rounded-xl border min-w-[90px] ${
              stage.status === 'success' ? 'border-green-500/30 bg-green-500/5' :
              stage.status === 'failed' ? 'border-red-500/30 bg-red-500/5' :
              stage.status === 'running' ? 'border-blue-500/30 bg-blue-500/5' :
              'border-slate-600 bg-slate-700/30'
            }`}>
              <StatusIcon status={stage.status} />
              <span className="text-xs text-slate-400 mt-1.5 text-center leading-tight">
                {i + 1}. {stage.stage.split(' ')[0]}
              </span>
            </div>
            {i < stages.length - 1 && (
              <ArrowRight className="w-4 h-4 text-slate-600 flex-shrink-0" />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function Pipeline() {
  const { data, isLoading, error, refetch } = usePipelineStatus()
  const trigger = useTriggerPipeline()
  const [triggered, setTriggered] = useState(false)

  const handleTrigger = async () => {
    await trigger.mutateAsync()
    setTriggered(true)
    setTimeout(() => setTriggered(false), 5000)
  }

  const stages = data?.stages || []

  return (
    <div className="p-4 lg:p-6 max-w-4xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Pipeline Status</h1>
          <p className="text-slate-400 text-sm mt-1">
            7-stage data pipeline — auto-refreshes every 30s
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={handleTrigger}
            disabled={trigger.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-teal-500 hover:bg-teal-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <Play className="w-4 h-4" />
            {trigger.isPending ? 'Triggering...' : triggered ? 'Queued!' : 'Trigger Pipeline'}
          </button>
        </div>
      </div>

      {triggered && (
        <div className="p-3 bg-teal-500/10 border border-teal-500/30 rounded-lg text-sm text-teal-300">
          Pipeline triggered! Run ID: {trigger.data?.dag_run_id}. Stages will update shortly.
        </div>
      )}

      {/* Overall status */}
      {data && (
        <div className="flex items-center gap-4 p-4 bg-slate-800 border border-slate-700 rounded-xl">
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${
              data.overall_status === 'success' ? 'bg-green-400 animate-pulse-slow' :
              data.overall_status === 'partial' ? 'bg-yellow-400' :
              'bg-slate-500'
            }`} />
            <span className="text-sm font-semibold text-slate-200">
              {data.overall_status === 'success' ? 'All systems operational' :
               data.overall_status === 'partial' ? 'Partial degradation' :
               'Unknown status'}
            </span>
          </div>
          {data.last_full_run && (
            <span className="text-xs text-slate-500">
              Last full run: {formatDate(data.last_full_run)}
            </span>
          )}
        </div>
      )}

      {/* Architecture diagram */}
      {stages.length > 0 && <PipelineDiagram stages={stages} />}

      {/* Stage list */}
      <div>
        <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Stage Details</h2>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(7)].map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}
          </div>
        ) : (
          <div className="space-y-3">
            {stages.map((stage, i) => (
              <PipelineStageCard key={i} stage={stage} index={i} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
