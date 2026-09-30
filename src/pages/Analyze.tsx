import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  BarChart2, ChevronLeft, Layers, AlertTriangle,
  Loader2, Satellite, Shield, Info, Database,
  Terminal, Activity, Zap
} from 'lucide-react'
import { getObservations, runChangeAnalysis } from '../utils/api'
import type { ObservationsResponse, TemporalObservation, ChangeAnalysisResult } from '../types/analysis'

const LABEL_COLORS: Record<string, string> = {
  REAL: 'text-emerald-400 border-emerald-400/50 bg-emerald-950/30',
  HEURISTIC: 'text-amber-400 border-amber-400/50 bg-amber-950/30',
  DEMO: 'text-cyan-400 border-cyan-400/50 bg-cyan-950/30',
  UNAVAILABLE: 'text-slate-400 border-slate-400/50 bg-slate-900/30',
}

const CHANGE_TYPE_COLORS: Record<string, string> = {
  construction: 'text-orange-400',
  clearance: 'text-rose-400',
  water_extent: 'text-blue-400',
  road_development: 'text-amber-400',
  vegetation_change: 'text-emerald-400',
  general_change: 'text-slate-300',
}

export default function Analyze() {
  const { assetId } = useParams<{ assetId?: string }>()
  const navigate = useNavigate()

  const [observations, setObservations] = useState<ObservationsResponse | null>(null)
  const [loadingObs, setLoadingObs] = useState(false)
  const [obsError, setObsError] = useState<string | null>(null)

  const [beforeObs, setBeforeObs] = useState<TemporalObservation | null>(null)
  const [afterObs, setAfterObs] = useState<TemporalObservation | null>(null)
  const [changeResult, setChangeResult] = useState<ChangeAnalysisResult | null>(null)
  const [runningChange, setRunningChange] = useState(false)
  const [changeError, setChangeError] = useState<string | null>(null)

  const [activeTab, setActiveTab] = useState<'timeline' | 'comparison' | 'change' | 'provenance'>('timeline')
  const [showChangeMap, setShowChangeMap] = useState(true)

  useEffect(() => {
    if (!assetId) return
    setLoadingObs(true)
    setObsError(null)
    getObservations(assetId)
      .then((res) => {
        setObservations(res)
        const obs = res.observations
        if (obs.length >= 2) {
          setBeforeObs(obs[0])
          setAfterObs(obs[obs.length - 1])
        } else if (obs.length === 1) {
          setBeforeObs(obs[0])
        }
      })
      .catch((e) => setObsError(e.message))
      .finally(() => setLoadingObs(false))
  }, [assetId])

  const handleRunChange = useCallback(async () => {
    if (!beforeObs || !afterObs) return
    setRunningChange(true)
    setChangeError(null)
    setChangeResult(null)
    try {
      const res = await runChangeAnalysis(beforeObs.asset_id, afterObs.asset_id)
      setChangeResult(res)
      setActiveTab('change')
    } catch (e) {
      setChangeError(e instanceof Error ? e.message : 'Change analysis failed')
    } finally {
      setRunningChange(false)
    }
  }, [beforeObs, afterObs])

  if (!assetId) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="min-h-screen pt-24 flex flex-col items-center justify-center gap-6 text-slate-600 font-mono">
        <Activity className="w-16 h-16 opacity-50" />
        <div className="text-center">
          <p className="text-cyan-400 font-bold uppercase tracking-widest text-lg">Target Not Acquired</p>
          <p className="text-slate-500 text-xs mt-2">Initialize discovery protocol to select an asset for analysis.</p>
        </div>
        <button onClick={() => navigate('/search')}
          className="px-6 py-3 bg-cyan-600/20 border border-cyan-500/50 hover:bg-cyan-600/40 text-cyan-400 text-sm font-bold tracking-widest rounded-lg transition-colors flex items-center gap-2">
          RETURN TO DISCOVERY
        </button>
      </motion.div>
    )
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="min-h-screen pt-20 pb-12 font-mono">
      
      {/* Header HUD */}
      <div className="border-b border-cyan-900/30 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40 shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
        <div className="container-app py-4">
          <div className="flex items-center gap-4">
            <button onClick={() => navigate('/search')} className="p-2 rounded bg-slate-800/50 hover:bg-cyan-900/50 hover:text-cyan-400 border border-slate-700/50 transition-all group">
              <ChevronLeft className="w-5 h-5 opacity-70 group-hover:opacity-100" />
            </button>
            <div className="flex-1">
              <h1 className="text-xl font-display font-bold text-white flex items-center gap-2 tracking-wide">
                <Activity className="w-5 h-5 text-cyan-400" />
                TEMPORAL ANALYSIS
              </h1>
              <div className="flex items-center gap-2 mt-1">
                <Terminal className="w-3 h-3 text-slate-500" />
                <p className="text-cyan-500 text-xs tracking-wider opacity-80">{assetId}</p>
              </div>
            </div>
            {observations && (
              <span className={`px-3 py-1 rounded border text-xs font-bold tracking-widest uppercase shadow-[0_0_10px_rgba(0,0,0,0.2)] ${LABEL_COLORS[observations.label]}`}>
                {observations.label}
              </span>
            )}
          </div>

          {/* Sub-Tabs */}
          <div className="flex gap-2 mt-6 overflow-x-auto scrollbar-none pb-1 border-b-2 border-slate-800/50">
            {(['timeline', 'comparison', 'change', 'provenance'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-2 text-xs font-bold uppercase tracking-widest border-b-2 transition-all shrink-0 ${
                  activeTab === tab
                    ? 'border-cyan-400 text-cyan-400 glow-text'
                    : 'border-transparent text-slate-500 hover:text-slate-300 hover:border-slate-700'
                }`}
              >
                {tab === 'comparison' ? 'SPLIT_VIEW' : tab}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="container-app py-8">
        {loadingObs && (
          <div className="flex flex-col items-center justify-center py-32 gap-4 text-cyan-500">
            <Loader2 className="w-10 h-10 animate-spin" />
            <span className="text-xs font-bold tracking-widest uppercase">Fetching Temporal Data...</span>
          </div>
        )}

        {obsError && (
          <div className="flex items-start gap-3 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-sm">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <span>CRITICAL ERROR: {obsError}</span>
          </div>
        )}

        {observations && (
          <AnimatePresence mode="wait">
            
            {/* TIMELINE */}
            {activeTab === 'timeline' && (
              <motion.div key="timeline" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }} className="flex flex-col gap-6">
                
                <div className="glass-panel p-4 rounded-xl flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Database className="w-4 h-4 text-cyan-400" />
                    <h2 className="text-sm font-bold text-cyan-100">
                      [{observations.total}] TEMPORAL NODES DETECTED
                    </h2>
                  </div>
                  <span className="text-[10px] text-slate-400 uppercase tracking-widest">Select T0 (Before) and T1 (After) parameters</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
                  {observations.observations.map((obs, idx) => (
                    <ObservationCard
                      key={obs.asset_id}
                      obs={obs}
                      index={idx}
                      isReference={obs.is_reference}
                      isBefore={beforeObs?.asset_id === obs.asset_id}
                      isAfter={afterObs?.asset_id === obs.asset_id}
                      onSelectBefore={() => setBeforeObs(obs)}
                      onSelectAfter={() => setAfterObs(obs)}
                    />
                  ))}
                </div>
                
                {/* Mission Control Slider Area */}
                {beforeObs && afterObs && (
                  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mt-8 glass-panel p-6 rounded-2xl relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-cyan-400 to-amber-500" />
                    <div className="flex flex-col md:flex-row items-center justify-between gap-6">
                      <div className="flex-1 flex flex-col items-center text-center">
                        <span className="text-[10px] text-blue-400 uppercase tracking-widest mb-1">T0 / Baseline</span>
                        <span className="text-lg font-bold text-white">{beforeObs.acquisition_time.slice(0, 10)}</span>
                        <span className="text-xs text-slate-500 mt-1">{beforeObs.sensor}</span>
                      </div>
                      
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-full max-w-[200px] h-px bg-slate-700 relative">
                           <div className="absolute left-1/2 -translate-x-1/2 -top-2 w-4 h-4 rounded-full bg-slate-800 border-2 border-cyan-500 shadow-[0_0_10px_rgba(6,182,212,0.5)]" />
                        </div>
                        <span className="text-[10px] text-cyan-500 uppercase tracking-widest">Delta</span>
                      </div>

                      <div className="flex-1 flex flex-col items-center text-center">
                        <span className="text-[10px] text-amber-400 uppercase tracking-widest mb-1">T1 / Target</span>
                        <span className="text-lg font-bold text-white">{afterObs.acquisition_time.slice(0, 10)}</span>
                        <span className="text-xs text-slate-500 mt-1">{afterObs.sensor}</span>
                      </div>
                    </div>
                    
                    <div className="mt-8 flex justify-center">
                      <button
                        onClick={handleRunChange}
                        disabled={runningChange}
                        className="group relative overflow-hidden px-8 py-3 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 disabled:opacity-50 text-slate-950 font-bold rounded-xl transition-all shadow-[0_0_20px_rgba(6,182,212,0.3)] hover:shadow-[0_0_30px_rgba(6,182,212,0.6)] flex items-center gap-3"
                      >
                         <div className="absolute inset-0 bg-white/20 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
                        {runningChange ? <Loader2 className="w-5 h-5 animate-spin relative z-10" /> : <Zap className="w-5 h-5 relative z-10" />}
                        <span className="relative z-10 uppercase tracking-widest">Execute Change Protocol</span>
                      </button>
                    </div>
                  </motion.div>
                )}
              </motion.div>
            )}

            {/* COMPARISON */}
            {activeTab === 'comparison' && (
              <motion.div key="comparison" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}>
                {!beforeObs || !afterObs ? (
                  <div className="flex flex-col items-center justify-center py-24 text-slate-500">
                     <Layers className="w-12 h-12 mb-4 opacity-30" />
                    <p className="uppercase tracking-widest text-sm">Parameters missing. Set T0 and T1 in timeline.</p>
                  </div>
                ) : (
                  <div className="grid md:grid-cols-2 gap-6">
                    <ImagePanel title="T0 [BEFORE]" color="blue" obs={beforeObs} />
                    <ImagePanel title="T1 [AFTER]" color="amber" obs={afterObs} />
                  </div>
                )}
              </motion.div>
            )}

            {/* CHANGE */}
            {activeTab === 'change' && (
              <motion.div key="change" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}>
                {changeError && (
                  <div className="mb-6 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-sm uppercase tracking-widest flex items-center gap-3">
                    <AlertTriangle className="w-5 h-5" />
                    {changeError}
                  </div>
                )}
                
                {runningChange && (
                  <div className="glass-panel rounded-2xl flex flex-col items-center justify-center py-32 gap-6 text-cyan-400 relative overflow-hidden">
                    <div className="absolute inset-0 animate-scanline" />
                    <Loader2 className="w-12 h-12 animate-spin relative z-10" />
                    <div className="text-center relative z-10">
                       <p className="text-lg font-bold tracking-widest uppercase">Processing</p>
                       <p className="text-xs text-slate-400 mt-2">Aligning pixels • Matching histograms • Computing deltas</p>
                    </div>
                  </div>
                )}

                {changeResult && !runningChange && (
                  <ChangeResultPanel result={changeResult} showMap={showChangeMap} onToggleMap={() => setShowChangeMap((v) => !v)} />
                )}

                {!changeResult && !runningChange && !changeError && (
                  <div className="flex flex-col items-center justify-center py-24 text-slate-500">
                    <Zap className="w-12 h-12 mb-4 opacity-30" />
                    <p className="uppercase tracking-widest text-sm">Execute Change Protocol to view results.</p>
                  </div>
                )}
              </motion.div>
            )}

            {/* PROVENANCE */}
            {activeTab === 'provenance' && (
              <motion.div key="provenance" initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 10 }}>
                <ProvenancePanel assetId={assetId} changeResult={changeResult} />
              </motion.div>
            )}
          </AnimatePresence>
        )}
      </div>
    </motion.div>
  )
}

function ObservationCard({ obs, index, isReference, isBefore, isAfter, onSelectBefore, onSelectAfter }: {
  obs: TemporalObservation; index: number; isReference: boolean; isBefore: boolean; isAfter: boolean; onSelectBefore: () => void; onSelectAfter: () => void
}) {
  return (
    <div className={`relative group rounded-xl border bg-slate-900/50 overflow-hidden transition-all duration-300 ${
      isReference ? 'border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.2)]' : isBefore ? 'border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.2)]' : isAfter ? 'border-amber-500/50 shadow-[0_0_15px_rgba(245,158,11,0.2)]' : 'border-slate-800 hover:border-slate-600'
    }`}>
      <div className="aspect-square bg-slate-950 relative">
        {obs.thumbnail_b64 || obs.asset_id ? (
            <img src={obs.thumbnail_b64 ? `data:image/jpeg;base64,${obs.thumbnail_b64}` : `/api/tiles/${obs.asset_id}/preview`} alt={obs.source} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-slate-700">
              <Satellite className="w-6 h-6" />
            </div>
          )}
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-slate-950/40 pointer-events-none" />
        
        {isReference && <span className="absolute top-2 left-2 px-1.5 py-0.5 bg-cyan-500 text-slate-950 text-[10px] font-bold rounded shadow-[0_0_10px_rgba(6,182,212,0.8)]">TARGET</span>}
        {isBefore && <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-blue-500 text-white text-[10px] font-bold rounded shadow-[0_0_10px_rgba(59,130,246,0.8)]">T0</span>}
        {isAfter && <span className="absolute top-2 right-2 px-1.5 py-0.5 bg-amber-500 text-slate-950 text-[10px] font-bold rounded shadow-[0_0_10px_rgba(245,158,11,0.8)]">T1</span>}
        
        {obs.cloud_cover > 0.5 && (
          <span className="absolute bottom-2 right-2 bg-amber-500/20 p-1 rounded backdrop-blur">
            <AlertTriangle className="w-3 h-3 text-amber-400" title="High cloud cover" />
          </span>
        )}
      </div>

      <div className="p-3">
        <p className="text-xs text-white font-bold tracking-wider truncate mb-0.5">{obs.acquisition_time.slice(0, 10)}</p>
        <p className="text-[10px] text-slate-500 truncate mb-2">{obs.sensor}</p>
        
        <div className="flex gap-1.5 mt-2">
          <button onClick={onSelectBefore}
            className={`flex-1 py-1 text-[10px] uppercase font-bold tracking-widest rounded transition-all ${
              isBefore ? 'bg-blue-500 text-white shadow-[0_0_10px_rgba(59,130,246,0.5)]' : 'bg-slate-800 text-slate-400 hover:text-blue-300 hover:bg-slate-700'
            }`}>
            T0
          </button>
          <button onClick={onSelectAfter}
            className={`flex-1 py-1 text-[10px] uppercase font-bold tracking-widest rounded transition-all ${
              isAfter ? 'bg-amber-500 text-slate-950 shadow-[0_0_10px_rgba(245,158,11,0.5)]' : 'bg-slate-800 text-slate-400 hover:text-amber-300 hover:bg-slate-700'
            }`}>
            T1
          </button>
        </div>
      </div>
    </div>
  )
}

function ImagePanel({ title, color, obs }: { title: string; color: string; obs: TemporalObservation }) {
  const colorMap: Record<string, { text: string; bg: string; border: string }> = {
    blue: { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
    amber: { text: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' }
  }
  const c = colorMap[color]

  return (
    <div className={`glass-panel rounded-2xl overflow-hidden border ${c.border}`}>
      <div className={`px-4 py-3 border-b ${c.border} ${c.bg} flex items-center justify-between`}>
        <span className={`text-xs font-bold tracking-widest uppercase ${c.text}`}>{title}</span>
        <span className="text-xs text-slate-400">{obs.acquisition_time.slice(0, 10)} // {obs.sensor}</span>
      </div>
      <div className="aspect-video bg-slate-950 relative group">
        {obs.thumbnail_b64 || obs.asset_id ? (
            <img src={obs.thumbnail_b64 ? `data:image/jpeg;base64,${obs.thumbnail_b64}` : `/api/tiles/${obs.asset_id}/preview`} alt={obs.source} className="w-full h-full object-contain" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-slate-800">
              <Satellite className="w-12 h-12" />
            </div>
          )}
      </div>
      <div className="px-4 py-3 flex items-center justify-between gap-3 text-[10px] text-slate-400 uppercase tracking-widest bg-slate-900/50">
        <div className="flex items-center gap-4">
          <span>Q: {(obs.quality_score * 100).toFixed(0)}%</span>
          {obs.cloud_cover >= 0 && <span className={obs.cloud_cover > 0.5 ? 'text-amber-400' : ''}>C: {(obs.cloud_cover * 100).toFixed(0)}%</span>}
        </div>
        <span className={`px-2 py-0.5 rounded border ${LABEL_COLORS[obs.label] ?? LABEL_COLORS.DEMO}`}>{obs.label}</span>
      </div>
    </div>
  )
}

function ChangeResultPanel({ result, showMap, onToggleMap }: { result: ChangeAnalysisResult; showMap: boolean; onToggleMap: () => void }) {
  const confidencePercent = (result.confidence * 100).toFixed(1)
  const scorePercent = (result.change_score * 100).toFixed(1)
  const isHighConf = result.confidence > 0.6
  
  const changeColor = isHighConf ? 'text-rose-400 glow-text-rose' : result.confidence > 0.3 ? 'text-amber-400' : 'text-slate-400'
  const typeColor = CHANGE_TYPE_COLORS[result.change_type] ?? 'text-slate-300'

  return (
    <div className="flex flex-col gap-6">
      
      {/* HUD Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="DELTA DETECTED" value={`${scorePercent}%`} color={changeColor} />
        <MetricCard label="CONFIDENCE" value={`${confidencePercent}%`} color={changeColor} />
        <MetricCard label="CLASSIFICATION" value={result.change_type.replace(/_/g, ' ')} color={typeColor} />
        <MetricCard label="SOURCE" value={result.method} color={LABEL_COLORS[result.label]?.split(' ')[0] ?? 'text-cyan-400'} />
      </div>

      {result.quality_flags.length > 0 && (
        <div className="flex flex-wrap gap-2 p-4 bg-amber-950/40 border border-amber-500/30 rounded-xl">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          {result.quality_flags.map((flag) => (
            <span key={flag} className="px-2.5 py-1 text-xs text-amber-300 bg-amber-500/20 border border-amber-500/30 rounded-md font-bold uppercase tracking-widest">{flag.replace(/_/g, ' ')}</span>
          ))}
        </div>
      )}

      {result.change_map_b64 && (
        <div className="glass-panel rounded-2xl overflow-hidden relative">
           <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-rose-500 to-transparent opacity-50" />
          <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between bg-slate-900/50">
            <span className="text-xs font-bold text-white flex items-center gap-2 tracking-widest uppercase">
              <Layers className="w-4 h-4 text-rose-400" />
              Overlay Viewport
            </span>
            <button onClick={onToggleMap} className="text-xs font-bold tracking-widest uppercase text-slate-500 hover:text-cyan-400 transition-colors">
              {showMap ? '[ HIDE ]' : '[ SHOW ]'}
            </button>
          </div>
          {showMap && (
            <div className="bg-slate-950 p-2">
               <img src={`data:image/jpeg;base64,${result.change_map_b64}`} alt="Change map" className="w-full rounded-xl object-contain border border-slate-800" />
            </div>
          )}
        </div>
      )}

      {result.note && (
        <div className="flex items-start gap-3 text-xs text-slate-400 p-4 glass-panel rounded-xl">
          <Info className="w-4 h-4 shrink-0 text-cyan-500" />
          <span className="uppercase tracking-wide leading-relaxed">{result.note}</span>
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="glass-panel p-5 rounded-2xl relative overflow-hidden group">
      <div className="absolute -inset-1 bg-gradient-to-r from-transparent via-white/5 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />
      <p className="text-[10px] font-bold text-slate-500 mb-2 tracking-widest uppercase">{label}</p>
      <p className={`text-2xl lg:text-3xl font-display font-bold uppercase truncate ${color}`}>{value}</p>
    </div>
  )
}

function ProvenancePanel({ assetId, changeResult }: { assetId: string; changeResult: ChangeAnalysisResult | null }) {
  return (
    <div className="flex flex-col gap-4 max-w-3xl mx-auto">
      <ProvenanceSection title="SCENE METADATA" icon={<Satellite className="w-4 h-4 text-cyan-400" />}>
        <ProvRow label="Asset ID" value={assetId} />
        <ProvRow label="Processing version" value="v2.0-glassmorphic" />
        <ProvRow label="Embedding model" value="openai/clip-vit-base-patch32 [LOCAL]" />
      </ProvenanceSection>

      {changeResult && (
        <ProvenanceSection title="COMPUTATION LOG" icon={<Terminal className="w-4 h-4 text-amber-400" />}>
          <ProvRow label="Candidate ID" value={changeResult.candidate_id ?? 'NULL'} />
          <ProvRow label="Execution Method" value={changeResult.method} />
          <ProvRow label="Detected Class" value={changeResult.change_type} />
          <ProvRow label="Earliest Trace" value={changeResult.earliest_obs || 'NULL'} />
          <ProvRow label="Algorithm" value="ORB Alignment -> Histogram Sync -> AbsDiff Heuristic" />
          <div className="mt-4 p-3 bg-slate-950 border border-amber-500/30 rounded text-xs text-amber-400 flex items-start gap-2">
            <Shield className="w-4 h-4 shrink-0" />
            <span className="uppercase leading-relaxed tracking-wider">LABEL: HEURISTIC. This output is generated via OpenCV image processing, not deep learning.</span>
          </div>
        </ProvenanceSection>
      )}

      <ProvenanceSection title="DATA HONESTY PROTOCOL" icon={<Shield className="w-4 h-4 text-emerald-400" />}>
        <div className="text-xs text-slate-400 leading-relaxed uppercase tracking-wider">
          Outputs are strictly flagged: <span className="text-emerald-400 font-bold">REAL</span> (verified),{' '}
          <span className="text-amber-400 font-bold">HEURISTIC</span> (rule-based),{' '}
          <span className="text-cyan-400 font-bold">DEMO</span> (synthetic), or{' '}
          <span className="text-slate-500 font-bold">UNAVAILABLE</span>.
          Zero fabrication policy active.
        </div>
      </ProvenanceSection>
    </div>
  )
}

function ProvenanceSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="glass-panel p-6 rounded-2xl">
      <h3 className="text-xs font-bold text-slate-300 flex items-center gap-2 mb-6 tracking-widest border-b border-slate-700/50 pb-3 uppercase">{icon}{title}</h3>
      <div className="flex flex-col gap-3">{children}</div>
    </div>
  )
}

function ProvRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-800/50 pb-2">
      <span className="text-[10px] text-slate-500 uppercase tracking-widest shrink-0">{label}</span>
      <span className="text-xs text-slate-300 text-right truncate max-w-sm">{value}</span>
    </div>
  )
}
