import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Search as SearchIcon, Upload, Filter, X,
  Calendar, Satellite, Shield, AlertTriangle, Loader2,
  GitCompareArrows, BarChart2, Star, Crosshair, Map as MapIcon
} from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { semanticSearch, imageSearch } from '../utils/api'
import type { SceneResult, SearchResponse } from '../types/analysis'

delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const EXAMPLE_QUERIES = [
  'newly built structures near a river',
  'large vehicle concentrations on open ground',
  'vegetation clearing near settlement',
  'water extent expansion',
  'road development in industrial area',
]

const LABEL_COLORS: Record<string, string> = {
  REAL: 'text-emerald-400 border-emerald-400/50 bg-emerald-950/30',
  HEURISTIC: 'text-amber-400 border-amber-400/50 bg-amber-950/30',
  DEMO: 'text-cyan-400 border-cyan-400/50 bg-cyan-950/30',
  UNAVAILABLE: 'text-slate-400 border-slate-400/50 bg-slate-900/30',
}

function MapFly({ results }: { results: SceneResult[] }) {
  const map = useMap()
  useEffect(() => {
    const pts = results.filter((r) => r.bbox.length === 4)
    if (pts.length > 0) {
      try {
        const bounds = L.latLngBounds(pts.map((r) => [
          (r.bbox[1] + r.bbox[3]) / 2,
          (r.bbox[0] + r.bbox[2]) / 2,
        ]))
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 })
      } catch { /* ignore */ }
    }
  }, [results, map])
  return null
}

export default function Search() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState('')
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [sensor, setSensor] = useState('')
  const [minQuality, setMinQuality] = useState(0)
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedResult, setSelectedResult] = useState<SceneResult | null>(null)

  const handleTextSearch = useCallback(async () => {
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const res = await semanticSearch({
        q: query,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sensor: sensor || undefined,
        min_quality: minQuality,
        top_k: 20,
      })
      setResponse(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed')
    } finally {
      setLoading(false)
    }
  }, [query, dateFrom, dateTo, sensor, minQuality])

  const handleImageSearch = useCallback(async () => {
    if (!imageFile) return
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const res = await imageSearch({
        image: imageFile,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sensor: sensor || undefined,
        min_quality: minQuality,
        top_k: 20,
      })
      setResponse(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Image search failed')
    } finally {
      setLoading(false)
    }
  }, [imageFile, dateFrom, dateTo, sensor, minQuality])

  const handleImageDrop = (file: File) => {
    setImageFile(file)
    const reader = new FileReader()
    reader.onload = (e) => setImagePreview(e.target?.result as string)
    reader.readAsDataURL(file)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleTextSearch()
  }

  const mapResults = response?.results.filter((r) => r.bbox.length === 4) ?? []

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen pt-24 pb-12"
    >
      <div className="container-app">
        {/* Header Console */}
        <div className="glass-panel p-6 rounded-2xl mb-6 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500 shadow-[0_0_10px_rgba(6,182,212,1)]" />
          
          <div className="flex flex-col gap-5">
            <div>
              <h1 className="text-3xl font-display font-bold text-white flex items-center gap-3">
                <Crosshair className="w-6 h-6 text-cyan-400" />
                Discovery Console
              </h1>
              <p className="text-slate-400 text-sm mt-1 font-mono">Input query parameters for semantic or visual retrieval</p>
            </div>

            {/* Search Input Group */}
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1 group">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <SearchIcon className="w-5 h-5 text-cyan-500/50 group-focus-within:text-cyan-400 transition-colors" />
                </div>
                <input
                  type="text"
                  placeholder="Initiate query... e.g., 'new construction near river'"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="w-full pl-12 pr-4 py-4 bg-slate-900/50 border border-slate-700/50 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/30 transition-all shadow-inner font-mono text-sm"
                />
              </div>
              
              <button
                onClick={handleTextSearch}
                disabled={!query.trim() || loading}
                className="px-6 py-4 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 disabled:hover:bg-cyan-600 text-slate-950 font-bold rounded-xl transition-all shadow-[0_0_15px_rgba(6,182,212,0.3)] hover:shadow-[0_0_25px_rgba(6,182,212,0.5)] flex items-center justify-center gap-2"
              >
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <SearchIcon className="w-5 h-5" />}
                EXECUTE
              </button>
              
              <button
                onClick={() => fileInputRef.current?.click()}
                className="px-4 py-4 bg-slate-800/80 hover:bg-slate-700 border border-slate-600/50 text-cyan-300 rounded-xl transition-all flex items-center justify-center gap-2 font-mono text-sm uppercase"
                title="Search by reference image"
              >
                <Upload className="w-4 h-4" />
                Image
              </button>
              
              <button
                onClick={() => setShowFilters((v) => !v)}
                className={`px-4 py-4 border rounded-xl transition-all flex items-center justify-center gap-2 font-mono text-sm uppercase ${
                  showFilters 
                    ? 'bg-cyan-500/20 border-cyan-500/50 text-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.2)]' 
                    : 'bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
                }`}
              >
                <Filter className="w-4 h-4" />
                Params
              </button>
              
              <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) handleImageDrop(f)
              }} />
            </div>

            {/* Example Queries */}
            {!response && !loading && (
              <div className="flex flex-wrap gap-2">
                <span className="text-xs font-mono text-slate-500 flex items-center mr-2">SUGGESTED:</span>
                {EXAMPLE_QUERIES.map((q) => (
                  <button
                    key={q}
                    onClick={() => { setQuery(q); setTimeout(handleTextSearch, 50) }}
                    className="px-3 py-1 bg-slate-800/50 hover:bg-slate-700 border border-slate-700/50 text-slate-400 hover:text-cyan-300 text-xs font-mono rounded-full transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            {/* Active Image Preview */}
            <AnimatePresence>
              {imagePreview && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-4 p-4 bg-slate-900/50 rounded-xl border border-cyan-500/30"
                >
                  <div className="relative w-16 h-16 rounded-lg overflow-hidden border border-slate-600">
                    <img src={imagePreview} alt="Query" className="w-full h-full object-cover" />
                    <div className="absolute inset-0 bg-cyan-500/10" />
                  </div>
                  <div className="flex-1 min-w-0 font-mono">
                    <p className="text-sm font-semibold text-cyan-400 truncate">{imageFile?.name}</p>
                    <p className="text-xs text-slate-500 mt-1">REFERENCE TARGET • {(imageFile!.size / 1024).toFixed(0)} KB</p>
                  </div>
                  <button
                    onClick={handleImageSearch}
                    disabled={loading}
                    className="px-4 py-2 bg-cyan-600/20 border border-cyan-500/50 hover:bg-cyan-600/40 text-cyan-300 text-xs font-bold font-mono rounded-lg transition-colors flex items-center gap-2 disabled:opacity-40"
                  >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <SearchIcon className="w-4 h-4" />}
                    FIND MATCHES
                  </button>
                  <button onClick={() => { setImageFile(null); setImagePreview(null) }} className="p-2 text-slate-500 hover:text-rose-400 transition-colors">
                    <X className="w-5 h-5" />
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Filter Drawer */}
            <AnimatePresence>
              {showFilters && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="grid grid-cols-2 md:grid-cols-4 gap-4 p-5 bg-slate-900/80 rounded-xl border border-slate-700/50 font-mono"
                >
                  <div>
                    <label className="text-xs text-slate-400 mb-2 flex items-center gap-1.5 uppercase tracking-wider"><Calendar className="w-3.5 h-3.5 text-cyan-500" /> Date T0</label>
                    <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-300 focus:outline-none focus:border-cyan-500/50 transition-colors" />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-2 flex items-center gap-1.5 uppercase tracking-wider"><Calendar className="w-3.5 h-3.5 text-cyan-500" /> Date T1</label>
                    <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-300 focus:outline-none focus:border-cyan-500/50 transition-colors" />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-2 flex items-center gap-1.5 uppercase tracking-wider"><Satellite className="w-3.5 h-3.5 text-cyan-500" /> Sensor</label>
                    <input type="text" placeholder="e.g. Sentinel" value={sensor} onChange={(e) => setSensor(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-300 placeholder-slate-600 focus:outline-none focus:border-cyan-500/50 transition-colors" />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 mb-2 flex items-center gap-1.5 uppercase tracking-wider"><Shield className="w-3.5 h-3.5 text-cyan-500" /> Min Quality [{minQuality.toFixed(1)}]</label>
                    <input type="range" min={0} max={1} step={0.1} value={minQuality} onChange={(e) => setMinQuality(Number(e.target.value))}
                      className="w-full accent-cyan-500 mt-2" />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Status Indicators */}
        {error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-6 flex items-start gap-3 p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-400 text-sm font-mono">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            <span>SYSTEM ERROR: {error}</span>
          </motion.div>
        )}

        {loading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center py-32 gap-4 text-cyan-500">
            <div className="relative">
               <Loader2 className="w-12 h-12 animate-spin" />
               <div className="absolute inset-0 bg-cyan-500 blur-xl opacity-20 animate-pulse" />
            </div>
            <p className="font-mono text-sm tracking-widest uppercase">Querying Vector Index...</p>
          </motion.div>
        )}

        {/* Results Area */}
        {response && !loading && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-6">
            
            {/* Meta Bar */}
            <div className="flex items-center justify-between px-2 font-mono text-sm">
              <div className="flex items-center gap-4">
                <span className="text-cyan-400 font-bold glow-text">{response.total} MATCHES FOUND</span>
                <span className={`px-2 py-0.5 rounded border text-[10px] uppercase font-bold tracking-wider ${LABEL_COLORS[response.label] ?? LABEL_COLORS.DEMO}`}>
                  {response.label}
                </span>
                {response.method && (
                  <span className="text-slate-500">VIA {response.method}</span>
                )}
              </div>
              {response.note && (
                <span className="text-amber-400 flex items-center gap-1.5 text-xs bg-amber-500/10 px-2 py-1 rounded border border-amber-500/20">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  {response.note}
                </span>
              )}
            </div>

            <div className="grid lg:grid-cols-12 gap-6">
              
              {/* Map Panel */}
              <div className="lg:col-span-5 glass-panel rounded-2xl overflow-hidden h-[400px] lg:h-[650px] relative dark-tiles">
                <div className="absolute top-4 left-4 z-[400] bg-slate-900/80 backdrop-blur border border-slate-700 px-3 py-1.5 rounded-lg flex items-center gap-2 font-mono text-xs text-cyan-400">
                  <MapIcon className="w-3.5 h-3.5" />
                  SPATIAL DISTRIBUTION
                </div>
                <MapContainer center={[20.5937, 78.9629]} zoom={4} className="w-full h-full" zoomControl={true}>
                  <TileLayer
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                    attribution="(c) Esri"
                  />
                  <MapFly results={mapResults} />
                  {mapResults.map((r) => (
                    <Marker key={r.asset_id} position={[(r.bbox[1] + r.bbox[3]) / 2, (r.bbox[0] + r.bbox[2]) / 2]}>
                      <Popup>
                        <div className="min-w-[160px] font-mono">
                          <p className="font-bold text-sm text-cyan-400 mb-1">{r.source}</p>
                          <p className="text-xs text-slate-400">{r.sensor} // {(r.acquisition_time || "").slice(0, 10)}</p>
                          <div className="mt-2 pt-2 border-t border-slate-700 flex justify-between items-center">
                            <span className="text-xs text-slate-500">CONFIDENCE</span>
                            <span className="text-xs text-white">{(r.similarity_score * 100).toFixed(1)}%</span>
                          </div>
                        </div>
                      </Popup>
                    </Marker>
                  ))}
                </MapContainer>
              </div>

              {/* Data Grid */}
              <div className="lg:col-span-7 flex flex-col gap-3 max-h-[650px] overflow-y-auto pr-2 custom-scrollbar">
                {response.results.length === 0 ? (
                  <div className="glass-panel h-full rounded-2xl flex flex-col items-center justify-center p-8 text-center text-slate-500">
                    <Crosshair className="w-12 h-12 mb-4 opacity-50" />
                    <p className="font-mono text-sm uppercase tracking-widest">No target matches acquired</p>
                    <p className="text-xs mt-2 opacity-70">Adjust parameters or query terms</p>
                  </div>
                ) : (
                  response.results.map((result, idx) => (
                    <ResultCard
                      key={result.asset_id}
                      result={result}
                      rank={idx + 1}
                      isSelected={selectedResult?.asset_id === result.asset_id}
                      onSelect={() => setSelectedResult(result)}
                      onAnalyze={() => navigate(`/analyze/${result.asset_id}`)}
                      onSimilar={() => navigate(`/similar-sites/${result.asset_id}`)}
                    />
                  ))
                )}
              </div>
            </div>
          </motion.div>
        )}

        {/* Initial Empty State */}
        {!response && !loading && !error && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }} className="flex flex-col items-center justify-center py-32 gap-6 text-slate-600">
            <div className="relative">
              <div className="absolute inset-0 bg-cyan-500/20 blur-2xl rounded-full" />
              <div className="w-20 h-20 rounded-2xl bg-slate-900 border border-slate-700 flex items-center justify-center relative z-10 shadow-xl shadow-cyan-900/10">
                <SearchIcon className="w-10 h-10 text-slate-500" />
              </div>
            </div>
            <div className="text-center font-mono">
              <p className="text-slate-400 font-bold tracking-wider uppercase mb-2">Awaiting Parameters</p>
              <p className="text-slate-600 text-xs">Enter semantic query or provide reference imagery above.</p>
            </div>
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}

function ResultCard({ result, rank, isSelected, onSelect, onAnalyze, onSimilar }: {
  result: SceneResult; rank: number; isSelected: boolean; onSelect: () => void; onAnalyze: () => void; onSimilar: () => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: rank * 0.03, type: "spring", stiffness: 200, damping: 20 }}
      onClick={onSelect}
      className={`relative group flex gap-4 p-4 rounded-xl border cursor-pointer transition-all duration-300 ${
        isSelected
          ? 'bg-cyan-900/20 border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.15)]'
          : 'bg-slate-900/40 border-slate-700/50 hover:bg-slate-800/60 hover:border-cyan-500/30'
      }`}
    >
      {isSelected && (
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-3/4 bg-cyan-400 rounded-r shadow-[0_0_10px_rgba(6,182,212,0.8)]" />
      )}

      {/* Rank Badge */}
      <div className="shrink-0 w-8 h-8 rounded bg-slate-950 border border-slate-800 flex items-center justify-center text-xs font-mono text-slate-400 shadow-inner group-hover:text-cyan-400 transition-colors">
        {rank.toString().padStart(2, '0')}
      </div>

      {/* Image Preview */}
      <div className="shrink-0 w-24 h-24 rounded-lg overflow-hidden bg-slate-950 border border-slate-700 relative">
        {result.thumbnail_b64 || (result as any).preview_url ? (
          <img src={result.thumbnail_b64 ? `data:image/jpeg;base64,${result.thumbnail_b64}` : (result as any).preview_url} alt={result.source} className="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-slate-700">
            <Satellite className="w-6 h-6" />
          </div>
        )}
        <div className="absolute inset-0 bg-cyan-500/0 group-hover:bg-cyan-500/10 transition-colors pointer-events-none" />
      </div>

      {/* Readouts */}
      <div className="flex-1 min-w-0 font-mono flex flex-col justify-between py-0.5">
        <div>
          <div className="flex items-start justify-between gap-2">
            <p className="text-sm font-bold text-white truncate group-hover:text-cyan-100 transition-colors">{result.source}</p>
            <div className="flex items-center gap-1.5 shrink-0 bg-slate-950 px-2 py-1 rounded border border-slate-800">
              <Star className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-xs font-bold text-cyan-400 glow-text">{(result.similarity_score * 100).toFixed(1)}%</span>
            </div>
          </div>
          <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
            <span className="flex items-center gap-1.5"><Satellite className="w-3.5 h-3.5" />{result.sensor}</span>
            <span className="flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" />{(result.acquisition_time || "").slice(0, 10)}</span>
          </div>
        </div>

        <div className="flex items-center justify-between mt-3">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider border ${LABEL_COLORS[result.label] ?? LABEL_COLORS.DEMO}`}>
              {result.label}
            </span>
             {result.cloud_cover >= 0 && (
              <span className={`text-[10px] px-2 py-0.5 rounded border ${result.cloud_cover > 0.5 ? 'border-amber-500/30 text-amber-400 bg-amber-500/10' : 'border-slate-700 text-slate-400 bg-slate-800'}`}>
                C: {(result.cloud_cover * 100).toFixed(0)}%
              </span>
            )}
          </div>
          
          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button onClick={(e) => { e.stopPropagation(); onSimilar() }} className="p-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition-colors" title="Find Similar Sites">
              <GitCompareArrows className="w-4 h-4" />
            </button>
            <button onClick={(e) => { e.stopPropagation(); onAnalyze() }} className="px-3 py-1.5 rounded bg-cyan-600/20 border border-cyan-500/50 text-cyan-400 font-bold text-xs hover:bg-cyan-600/40 transition-colors flex items-center gap-1.5">
              <BarChart2 className="w-3.5 h-3.5" />
              ANALYZE
            </button>
          </div>
        </div>
      </div>
    </motion.div>
  )
}
