import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ClipboardCheck, CheckCircle2, XCircle, AlertCircle,
  Loader2, AlertTriangle, Satellite, Layers,
  ChevronDown, ChevronUp, Info, RefreshCw, Terminal, Target
} from 'lucide-react'
import { getReviewQueue, submitReviewDecision } from '../utils/api'
import type { ReviewQueue, ReviewItem } from '../types/analysis'

const STATUS_COLORS: Record<string, string> = {
  NEW: 'text-cyan-400 border-cyan-400/50 bg-cyan-950/30',
  CONFIRMED: 'text-emerald-400 border-emerald-400/50 bg-emerald-950/30',
  REJECTED: 'text-rose-400 border-rose-400/50 bg-rose-950/30',
  NEEDS_REVIEW: 'text-amber-400 border-amber-400/50 bg-amber-950/30',
}

const STATUS_FILTERS = ['All', 'NEW', 'CONFIRMED', 'REJECTED', 'NEEDS_REVIEW'] as const
type StatusFilter = (typeof STATUS_FILTERS)[number]

export default function Review() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('All')
  const [queue, setQueue] = useState<ReviewQueue | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState<string | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})

  const loadQueue = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getReviewQueue(statusFilter === 'All' ? undefined : statusFilter)
      setQueue(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load queue')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { loadQueue() }, [loadQueue])

  const handleDecision = async (candidateId: string, status: 'CONFIRMED' | 'REJECTED' | 'NEEDS_REVIEW') => {
    setSubmitting(candidateId)
    try {
      await submitReviewDecision({
        candidate_id: candidateId,
        status,
        notes: notes[candidateId] ?? '',
      })
      await loadQueue()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Decision failed')
    } finally {
      setSubmitting(null)
    }
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="min-h-screen pt-20 pb-12 font-mono">
      
      {/* Header HUD */}
      <div className="border-b border-cyan-900/30 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40 shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
        <div className="container-app py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-display font-bold text-white flex items-center gap-2 tracking-wide">
              <ClipboardCheck className="w-5 h-5 text-cyan-400" />
              ANALYST TRIAGE
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <Terminal className="w-3 h-3 text-slate-500" />
              <p className="text-cyan-500 text-xs tracking-wider opacity-80">Awaiting Human-in-the-Loop Verification</p>
            </div>
          </div>
          
          <button onClick={loadQueue} disabled={loading}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold uppercase tracking-widest text-cyan-400 hover:text-cyan-300 bg-cyan-950/30 hover:bg-cyan-900/50 border border-cyan-500/30 hover:border-cyan-400/50 rounded-lg transition-all shadow-[0_0_10px_rgba(6,182,212,0.1)] hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] disabled:opacity-50">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-white' : ''}`} />
            Sync Queue
          </button>
        </div>

        {/* Status Filters */}
        <div className="container-app">
          <div className="flex gap-2 mt-2 overflow-x-auto scrollbar-none pb-1 border-b-2 border-slate-800/50">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setStatusFilter(f)}
                className={`px-4 py-2 text-xs font-bold uppercase tracking-widest border-b-2 transition-all shrink-0 ${
                  statusFilter === f
                    ? 'border-cyan-400 text-cyan-400 glow-text'
                    : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-700'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="container-app py-8 max-w-4xl">
        {error && (
          <div className="mb-6 flex items-start gap-3 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-sm">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <span>TRIAGE ERROR: {error}</span>
          </div>
        )}

        {loading && !queue && (
          <div className="flex flex-col items-center justify-center py-32 gap-4 text-cyan-500">
            <Loader2 className="w-10 h-10 animate-spin" />
            <span className="text-xs font-bold tracking-widest uppercase">Fetching Review Queue...</span>
          </div>
        )}

        {queue && (
          <div className="flex flex-col gap-4">
            {queue.items.length === 0 ? (
              <div className="glass-panel h-[400px] rounded-2xl flex flex-col items-center justify-center p-8 text-center text-slate-500">
                <Target className="w-12 h-12 mb-4 opacity-50" />
                <p className="font-mono text-sm uppercase tracking-widest font-bold">No Candidates in Queue</p>
                <p className="text-xs mt-2 opacity-70">Execute change analysis protocols to generate review items.</p>
                <button onClick={() => navigate('/analyze')}
                  className="mt-6 px-6 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold uppercase tracking-widest rounded transition-colors border border-slate-600">
                  Switch to Analyze
                </button>
              </div>
            ) : (
              queue.items.map((item) => (
                <ReviewCard
                  key={item.candidate_id}
                  item={item}
                  isExpanded={expandedId === item.candidate_id}
                  isSubmitting={submitting === item.candidate_id}
                  notes={notes[item.candidate_id] ?? ''}
                  onToggle={() => setExpandedId((v) => v === item.candidate_id ? null : item.candidate_id)}
                  onNotesChange={(v) => setNotes((prev) => ({ ...prev, [item.candidate_id]: v }))}
                  onDecision={(status) => handleDecision(item.candidate_id, status)}
                />
              ))
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}

function ReviewCard({
  item, isExpanded, isSubmitting, notes, onToggle, onNotesChange, onDecision,
}: {
  item: ReviewItem
  isExpanded: boolean
  isSubmitting: boolean
  notes: string
  onToggle: () => void
  onNotesChange: (v: string) => void
  onDecision: (status: 'CONFIRMED' | 'REJECTED' | 'NEEDS_REVIEW') => void
}) {
  const confidenceColor = item.confidence > 0.6 ? 'text-rose-400' : item.confidence > 0.3 ? 'text-amber-400' : 'text-slate-400'
  const isHighConf = item.confidence > 0.6

  return (
    <div className={`relative rounded-xl border bg-slate-900/60 overflow-hidden transition-all duration-300 ${
      isExpanded 
        ? 'border-cyan-500/50 shadow-[0_0_20px_rgba(6,182,212,0.15)]' 
        : 'border-slate-800 hover:border-slate-600 hover:bg-slate-800/50'
    }`}>
       {isExpanded && (
        <div className="absolute left-0 top-0 w-1 h-full bg-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.8)]" />
      )}

      {/* Summary Row */}
      <button onClick={onToggle} className="w-full flex flex-col sm:flex-row sm:items-center gap-4 p-4 text-left transition-colors relative z-10">
        
        {/* Thumbnails */}
        <div className="flex gap-2 shrink-0">
          {[item.scene_before, item.scene_after].map((scene, i) => (
            <div key={i} className="relative w-14 h-14 rounded-lg bg-slate-950 border border-slate-700 overflow-hidden">
               {scene?.thumbnail_b64 ? (
                 <img src={`data:image/jpeg;base64,${scene.thumbnail_b64}`} alt="" className="w-full h-full object-cover" />
               ) : (
                 <div className="w-full h-full flex items-center justify-center">
                   <Satellite className="w-5 h-5 text-slate-600" />
                 </div>
               )}
               <div className="absolute top-0 right-0 bg-slate-950/80 text-[8px] px-1 py-0.5 font-bold tracking-widest text-slate-400">
                  {i === 0 ? 'T0' : 'T1'}
               </div>
            </div>
          ))}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0 flex flex-col justify-center">
          <div className="flex items-center gap-2 mb-1">
             <span className={`shrink-0 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest border ${STATUS_COLORS[item.status] ?? STATUS_COLORS.NEW}`}>
               {item.status}
             </span>
             <p className="text-sm font-bold text-white uppercase tracking-wider truncate">{item.change_type.replace(/_/g, ' ')}</p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs text-slate-500">
             <span>{item.scene_before?.acquisition_time.slice(0, 10) || 'N/A'}</span>
             <span className="text-cyan-500/50">→</span>
             <span>{item.scene_after?.acquisition_time.slice(0, 10) || 'N/A'}</span>
          </div>
        </div>

        {/* Right Actions */}
        <div className="flex items-center justify-between sm:justify-end gap-6 w-full sm:w-auto mt-2 sm:mt-0">
          <div className="text-right">
            <p className={`text-xl font-display font-bold ${confidenceColor} ${isHighConf ? 'glow-text-rose' : ''}`}>{(item.confidence * 100).toFixed(1)}%</p>
            <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold">Confidence</p>
          </div>
          <div className="shrink-0 w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-slate-400">
            {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </div>
        </div>
      </button>

      {/* Expanded Details */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden bg-slate-950/50"
          >
            <div className="px-5 pb-5 flex flex-col gap-6 border-t border-slate-800/50 pt-5">
              
              {/* Metrics HUD */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricBox label="Change Delta" value={`${(item.change_score * 100).toFixed(1)}%`} />
                <MetricBox label="Confidence" value={`${(item.confidence * 100).toFixed(1)}%`} color={confidenceColor} />
                <MetricBox label="Method" value={item.method} />
                <MetricBox label="Candidate ID" value={item.candidate_id.split('-')[0]} />
              </div>

              {item.quality_flags.length > 0 && (
                <div className="flex flex-wrap gap-2 p-3 bg-amber-950/40 border border-amber-500/30 rounded-xl">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  {item.quality_flags.map((f) => (
                    <span key={f} className="text-[10px] font-bold uppercase tracking-widest text-amber-300 bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/30">{f.replace(/_/g, ' ')}</span>
                  ))}
                </div>
              )}

              {item.change_map_b64 && (
                <div className="rounded-xl overflow-hidden border border-slate-700 bg-black relative">
                   <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-rose-500 to-transparent opacity-50 z-10" />
                  <div className="px-3 py-2 bg-slate-900 border-b border-slate-700 text-[10px] font-bold uppercase tracking-widest text-slate-400 flex items-center gap-2">
                    <Layers className="w-3.5 h-3.5" /> Overlay Viewport
                  </div>
                  <img src={`data:image/jpeg;base64,${item.change_map_b64}`} alt="Change map" className="w-full object-contain" />
                </div>
              )}

              {/* Triage Console */}
              <div className="glass-panel p-4 rounded-xl">
                 <h3 className="text-xs font-bold text-cyan-400 flex items-center gap-2 mb-3 uppercase tracking-widest">
                    <Terminal className="w-4 h-4" /> Action Console
                 </h3>
                 
                 <div className="mb-4">
                  <label className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-2 block">Analyst Assessment Log</label>
                  <textarea
                    value={notes}
                    onChange={(e) => onNotesChange(e.target.value)}
                    rows={2}
                    placeholder="Enter verification notes or reasoning..."
                    className="w-full px-4 py-3 bg-slate-950 border border-slate-700/50 rounded-lg text-sm text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20 resize-none font-mono transition-all"
                  />
                 </div>

                 {item.decision && (
                  <div className="flex items-start gap-2 text-xs text-slate-400 p-3 bg-slate-950 rounded border border-slate-800 mb-4 font-mono">
                    <Info className="w-4 h-4 shrink-0 text-cyan-500 mt-0.5" />
                    <div>
                       <span className="text-slate-300">USER {item.decision.analyst_id}</span> on <span className="text-slate-300">{new Date(item.decision.timestamp * 1000).toLocaleString()}</span>
                       {item.decision.notes && <div className="mt-1 text-amber-400/80">"{item.decision.notes}"</div>}
                    </div>
                  </div>
                 )}

                 <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <DecisionButton 
                     id={`confirm-btn-${item.candidate_id}`}
                     onClick={() => onDecision('CONFIRMED')}
                     disabled={isSubmitting}
                     loading={isSubmitting}
                     icon={<CheckCircle2 className="w-4 h-4" />}
                     label="CONFIRM"
                     colorClass="bg-emerald-950/50 hover:bg-emerald-900/60 text-emerald-400 border-emerald-500/30 hover:border-emerald-400/50 shadow-[0_0_10px_rgba(16,185,129,0.1)] hover:shadow-[0_0_15px_rgba(16,185,129,0.2)]"
                  />
                  <DecisionButton 
                     id={`reject-btn-${item.candidate_id}`}
                     onClick={() => onDecision('REJECTED')}
                     disabled={isSubmitting}
                     loading={isSubmitting}
                     icon={<XCircle className="w-4 h-4" />}
                     label="REJECT"
                     colorClass="bg-rose-950/50 hover:bg-rose-900/60 text-rose-400 border-rose-500/30 hover:border-rose-400/50 shadow-[0_0_10px_rgba(244,63,94,0.1)] hover:shadow-[0_0_15px_rgba(244,63,94,0.2)]"
                  />
                  <DecisionButton 
                     id={`flag-btn-${item.candidate_id}`}
                     onClick={() => onDecision('NEEDS_REVIEW')}
                     disabled={isSubmitting}
                     loading={isSubmitting}
                     icon={<AlertCircle className="w-4 h-4" />}
                     label="FLAG"
                     colorClass="bg-amber-950/50 hover:bg-amber-900/60 text-amber-400 border-amber-500/30 hover:border-amber-400/50 shadow-[0_0_10px_rgba(245,158,11,0.1)] hover:shadow-[0_0_15px_rgba(245,158,11,0.2)]"
                  />
                 </div>
              </div>

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function MetricBox({ label, value, color = "text-white" }: { label: string, value: string, color?: string }) {
   return (
      <div className="p-3 bg-slate-900 border border-slate-800 rounded-lg text-center relative overflow-hidden group">
         <div className="absolute inset-0 bg-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity" />
         <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-1">{label}</p>
         <p className={`text-lg font-bold font-display ${color} truncate`}>{value}</p>
      </div>
   )
}

function DecisionButton({ id, onClick, disabled, loading, icon, label, colorClass }: {
   id: string, onClick: () => void, disabled: boolean, loading: boolean, icon: React.ReactNode, label: string, colorClass: string
}) {
   return (
      <button
         id={id}
         onClick={onClick}
         disabled={disabled}
         className={`flex items-center justify-center gap-2 py-3 rounded-lg border font-bold text-xs tracking-widest uppercase transition-all disabled:opacity-50 disabled:pointer-events-none relative overflow-hidden ${colorClass}`}
      >
         {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : icon}
         {label}
      </button>
   )
}
