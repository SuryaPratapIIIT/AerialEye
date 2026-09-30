import { useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  Database, Upload, CheckCircle2, AlertTriangle, Loader2,
  RefreshCw, HardDrive, Cpu, Layers, Server, Info, X,
  Terminal, Activity, Zap
} from 'lucide-react'
import { getDataStatus, ingestImage } from '../utils/api'
import type { DataStatus, IngestResult } from '../types/analysis'

interface IngestJob {
  id: string
  filename: string
  status: 'pending' | 'success' | 'skipped' | 'error'
  result?: IngestResult
  error?: string
}

export default function Data() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [status, setStatus] = useState<DataStatus | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(false)
  const [jobs, setJobs] = useState<IngestJob[]>([])
  const [dragging, setDragging] = useState(false)

  const loadStatus = useCallback(async () => {
    setLoadingStatus(true)
    try {
      const s = await getDataStatus()
      setStatus(s)
    } catch { /* ignore */ } finally {
      setLoadingStatus(false)
    }
  }, [])

  useEffect(() => { loadStatus() }, [loadStatus])

  const ingestFiles = async (files: File[]) => {
    const newJobs: IngestJob[] = files.map((f) => ({
      id: `${f.name}-${Date.now()}`,
      filename: f.name,
      status: 'pending',
    }))
    setJobs((prev) => [...newJobs, ...prev])

    for (const job of newJobs) {
      const file = files.find((f) => f.name === job.filename)!
      try {
        const result = await ingestImage({ file, label: 'REAL' })
        setJobs((prev) =>
          prev.map((j) =>
            j.id === job.id
              ? { ...j, status: result.status === 'skipped' ? 'skipped' : 'success', result }
              : j,
          ),
        )
      } catch (e) {
        setJobs((prev) =>
          prev.map((j) =>
            j.id === job.id
              ? { ...j, status: 'error', error: e instanceof Error ? e.message : 'Unknown error' }
              : j,
          ),
        )
      }
    }
    loadStatus()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer.files).filter((f) =>
      /\.(jpg|jpeg|png|tif|tiff|webp)$/i.test(f.name)
    )
    if (files.length) ingestFiles(files)
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="min-h-screen pt-20 pb-12 font-mono">
      
      {/* Header HUD */}
      <div className="border-b border-cyan-900/30 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40 shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
        <div className="container-app py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-display font-bold text-white flex items-center gap-2 tracking-wide">
              <Database className="w-5 h-5 text-cyan-400" />
              SYSTEM ARCHIVE
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <Terminal className="w-3 h-3 text-slate-500" />
              <p className="text-cyan-500 text-xs tracking-wider opacity-80">Vector Index & Telemetry</p>
            </div>
          </div>
          
          <button onClick={loadStatus} disabled={loadingStatus}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold uppercase tracking-widest text-cyan-400 hover:text-cyan-300 bg-cyan-950/30 hover:bg-cyan-900/50 border border-cyan-500/30 hover:border-cyan-400/50 rounded-lg transition-all shadow-[0_0_10px_rgba(6,182,212,0.1)] hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] disabled:opacity-50">
            <RefreshCw className={`w-4 h-4 ${loadingStatus ? 'animate-spin text-white' : ''}`} />
            Sync Telemetry
          </button>
        </div>
      </div>

      <div className="container-app py-8 flex flex-col gap-8 max-w-5xl">
        
        {/* Core Metrics Array */}
        {status && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatBox icon={<Layers className="w-5 h-5" />} color="cyan" label="Indexed Assets" value={String(status.index_stats.scene_count)} />
            <StatBox icon={<Cpu className="w-5 h-5" />} color="violet" label="Vector Embeddings" value={String(status.index_stats.embedding_count)} />
            <StatBox icon={<Zap className="w-5 h-5" />} color="amber" label="Change Candidates" value={String(status.index_stats.change_candidate_count)} />
            <StatBox icon={<HardDrive className="w-5 h-5" />} color="emerald" label="DB Size" value={`${(status.index_stats.db_size_bytes / 1024).toFixed(0)} KB`} />
          </div>
        )}

        {/* System Diagnostics */}
        {status && (
          <div className="glass-panel p-6 rounded-2xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500 shadow-[0_0_10px_rgba(6,182,212,1)]" />
            
            <h2 className="text-xs font-bold text-white flex items-center gap-2 tracking-widest uppercase mb-6">
              <Server className="w-4 h-4 text-cyan-400" />
              Service Diagnostics
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <ModelDiagNode label="CLIP Core" available={status.model_status.clip_available} info="openai/clip-vit-base-patch32" />
              <ModelDiagNode label="FAISS Engine" available={status.model_status.faiss_available} info={`${status.model_status.faiss_vector_count} vectors loaded`} />
              <ModelDiagNode label="YOLO Pipeline" available={status.yolo_available} info={status.yolo_model_path} />
              <ModelDiagNode label="Vision Interface" available={status.vision_api_key_loaded} info="Groq API key required" />
            </div>

            {!status.model_status.clip_available && (
              <div className="mt-6 flex items-start gap-3 text-xs text-amber-400 p-4 bg-amber-950/40 border border-amber-500/30 rounded-lg shadow-inner">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="flex flex-col gap-1">
                   <span className="font-bold uppercase tracking-widest">CLIP Engine Offline</span>
                   <span className="opacity-80">Semantic mapping disabled. Run <code className="bg-slate-900 px-1.5 py-0.5 rounded border border-slate-700">pip install sentence-transformers torch torchvision</code> to initialize.</span>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
           
           {/* Ingestion Uplink */}
           <div className="lg:col-span-5 flex flex-col gap-4">
             <div className="glass-panel p-6 rounded-2xl h-full flex flex-col">
               <h2 className="text-xs font-bold text-white flex items-center gap-2 tracking-widest uppercase mb-6">
                 <Upload className="w-4 h-4 text-cyan-400" />
                 Secure Uplink
               </h2>
               
               <div
                 onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
                 onDragLeave={() => setDragging(false)}
                 onDrop={handleDrop}
                 onClick={() => fileInputRef.current?.click()}
                 className={`flex-1 min-h-[200px] border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-300 relative overflow-hidden group ${
                   dragging ? 'border-cyan-500 bg-cyan-900/20 shadow-[inset_0_0_30px_rgba(6,182,212,0.2)]' : 'border-slate-700 hover:border-cyan-500/50 hover:bg-slate-800/50'
                 }`}
               >
                 <div className="absolute inset-0 bg-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                 <Upload className={`w-12 h-12 mb-4 transition-colors duration-300 ${dragging ? 'text-cyan-400' : 'text-slate-600 group-hover:text-cyan-500/50'}`} />
                 <p className="text-white font-bold tracking-widest uppercase text-sm mb-2">Transmit Assets</p>
                 <p className="text-slate-500 text-xs">Drag payload here or click to interface</p>
                 <p className="text-slate-600 text-[10px] uppercase tracking-widest mt-4">Formats: JPG, PNG, TIFF, WEBP // 50MB Max</p>
               </div>
               
               <input
                 ref={fileInputRef}
                 type="file"
                 accept=".jpg,.jpeg,.png,.tif,.tiff,.webp"
                 multiple
                 className="hidden"
                 onChange={(e) => {
                   const files = Array.from(e.target.files ?? [])
                   if (files.length) ingestFiles(files)
                   e.target.value = ''
                 }}
               />
             </div>
           </div>

           {/* Ingestion Matrix */}
           <div className="lg:col-span-7 flex flex-col gap-4">
             <div className="glass-panel p-6 rounded-2xl h-[400px] flex flex-col">
               <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-700/50">
                 <h2 className="text-xs font-bold text-white flex items-center gap-2 tracking-widest uppercase">
                    <Activity className="w-4 h-4 text-cyan-400" />
                    Uplink Matrix
                 </h2>
                 <button onClick={() => setJobs([])} className="text-[10px] uppercase font-bold tracking-widest text-slate-500 hover:text-cyan-400 flex items-center gap-1 transition-colors">
                   <X className="w-3 h-3" /> Purge Log
                 </button>
               </div>
               
               <div className="flex-1 overflow-y-auto custom-scrollbar pr-2 flex flex-col gap-3">
                 {jobs.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-slate-600">
                       <Terminal className="w-8 h-8 mb-3 opacity-30" />
                       <p className="text-xs font-bold uppercase tracking-widest">Matrix Idle</p>
                    </div>
                 ) : (
                    jobs.map((job) => (
                      <div key={job.id} className="flex items-center gap-4 p-3 rounded-xl bg-slate-900/60 border border-slate-800">
                        <div className="shrink-0 w-8 h-8 rounded bg-slate-950 flex items-center justify-center border border-slate-800">
                          {job.status === 'pending' && <Loader2 className="w-4 h-4 animate-spin text-cyan-500" />}
                          {job.status === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
                          {job.status === 'skipped' && <Info className="w-4 h-4 text-slate-500" />}
                          {job.status === 'error' && <AlertTriangle className="w-4 h-4 text-rose-400" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-bold text-white truncate tracking-wide">{job.filename}</p>
                          <div className="mt-1">
                             {job.status === 'success' && job.result && (
                               <div className="flex items-center gap-2">
                                  <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest bg-emerald-500/10 px-1.5 rounded">Parsed</span>
                                  <span className="text-[10px] text-slate-500 uppercase tracking-widest">Q: {((job.result.quality_score ?? 0) * 100).toFixed(0)}%</span>
                                  <span className="text-[10px] text-slate-500 uppercase tracking-widest">{job.result.embedding_available ? 'Embedded' : 'No Vector'}</span>
                               </div>
                             )}
                             {job.status === 'skipped' && <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">Duplicate signature ignored</p>}
                             {job.status === 'error' && <p className="text-[10px] font-bold text-rose-400 uppercase tracking-widest truncate">{job.error}</p>}
                             {job.status === 'pending' && <p className="text-[10px] font-bold text-cyan-500 uppercase tracking-widest animate-pulse">Processing Block...</p>}
                          </div>
                        </div>
                      </div>
                    ))
                 )}
               </div>
             </div>
           </div>
        </div>

        {/* Telemetry Footer */}
        {status && (
          <div className="flex items-center justify-between text-[10px] text-slate-500 uppercase tracking-widest font-bold">
            <div className="flex items-center gap-2">
              <HardDrive className="w-3.5 h-3.5" />
              Target DIR: <code className="text-cyan-500 bg-slate-900 px-2 py-0.5 rounded border border-slate-700">{status.data_dir}</code>
            </div>
            <span>AERIALEYE v2.0 SYSTEM READY</span>
          </div>
        )}
      </div>
    </motion.div>
  )
}

function StatBox({ icon, color, label, value }: { icon: React.ReactNode, color: 'cyan' | 'violet' | 'amber' | 'emerald', label: string, value: string }) {
   const colorMap = {
      cyan: 'text-cyan-400',
      violet: 'text-violet-400',
      amber: 'text-amber-400',
      emerald: 'text-emerald-400'
   }
   return (
    <div className="glass-panel p-4 rounded-xl flex items-center gap-4 relative overflow-hidden group">
      <div className="absolute inset-0 bg-white/5 translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
      <div className={`shrink-0 w-10 h-10 rounded-lg bg-slate-900 border border-slate-700 flex items-center justify-center ${colorMap[color]} shadow-inner`}>
         {icon}
      </div>
      <div className="relative z-10">
        <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-0.5 font-bold">{label}</p>
        <p className={`text-xl font-display font-bold ${colorMap[color]}`}>{value}</p>
      </div>
    </div>
  )
}

function ModelDiagNode({ label, available, info }: { label: string; available: boolean; info: string }) {
  return (
    <div className="glass-panel p-4 rounded-xl relative group">
       <div className={`absolute top-0 right-0 w-8 h-8 flex items-center justify-center`}>
          <div className={`w-2 h-2 rounded-full shadow-[0_0_10px_currentColor] ${available ? 'bg-emerald-400 text-emerald-400' : 'bg-rose-500 text-rose-500'}`} />
       </div>
      <p className="text-xs font-bold text-white mb-1 uppercase tracking-widest pr-6">{label}</p>
      <p className="text-[10px] text-slate-500 font-mono truncate">{info}</p>
    </div>
  )
}
