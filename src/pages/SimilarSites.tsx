import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  GitCompareArrows, ChevronLeft, Loader2, AlertTriangle,
  Satellite, Star, BarChart2, Search as SearchIcon,
  Activity, MapPin, Database
} from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { getSimilarSites } from '../utils/api'
import type { SearchResponse, SceneResult } from '../types/analysis'

delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const LABEL_COLORS: Record<string, string> = {
  REAL: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
  HEURISTIC: 'text-amber-400 border-amber-400/30 bg-amber-400/10',
  DEMO: 'text-cyan-400 border-cyan-400/30 bg-cyan-400/10',
  UNAVAILABLE: 'text-slate-400 border-slate-400/30 bg-slate-400/10',
}

function MapFly({ results }: { results: SceneResult[] }) {
  const map = useMap()
  useEffect(() => {
    const pts = results.filter((r) => r.bbox.length === 4)
    if (pts.length > 0) {
      try {
        const bounds = L.latLngBounds(pts.map((r) => [(r.bbox[1] + r.bbox[3]) / 2, (r.bbox[0] + r.bbox[2]) / 2]))
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 })
      } catch { /* ignore */ }
    }
  }, [results, map])
  return null
}

export default function SimilarSites() {
  const { assetId } = useParams<{ assetId?: string }>()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState<SearchResponse & { reference_asset_id?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<SceneResult | null>(null)

  useEffect(() => {
    if (!assetId) return
    setLoading(true)
    setError(null)
    getSimilarSites(assetId, 12)
      .then(setResponse)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [assetId])

  const mapResults = response?.results.filter((r) => r.bbox.length === 4) ?? []

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="min-h-screen pt-20 pb-12 font-mono">
      
      {/* HUD Header */}
      <div className="border-b border-cyan-900/30 bg-slate-900/80 backdrop-blur-md sticky top-0 z-40 shadow-[0_4px_30px_rgba(0,0,0,0.5)]">
        <div className="container-app py-4 flex items-center justify-between gap-3">
          <div className="flex items-center gap-4">
             <button onClick={() => navigate(-1)} className="w-8 h-8 rounded-lg bg-slate-800/50 border border-slate-700 flex items-center justify-center text-slate-400 hover:text-cyan-400 hover:border-cyan-500/50 transition-all">
               <ChevronLeft className="w-5 h-5" />
             </button>
             <div>
               <h1 className="text-xl font-display font-bold text-white flex items-center gap-2 tracking-wide uppercase">
                 <GitCompareArrows className="w-5 h-5 text-cyan-400" />
                 Spatial Correlation
               </h1>
               {assetId ? (
                 <div className="flex items-center gap-2 mt-1">
                   <Activity className="w-3 h-3 text-cyan-500" />
                   <p className="text-cyan-500 text-xs tracking-wider opacity-80 uppercase">Target: {assetId}</p>
                 </div>
               ) : (
                 <div className="flex items-center gap-2 mt-1">
                   <AlertTriangle className="w-3 h-3 text-amber-500" />
                   <p className="text-amber-500 text-xs tracking-wider opacity-80 uppercase">No target acquired</p>
                 </div>
               )}
             </div>
          </div>
          {response && (
            <span className={`px-3 py-1 rounded border text-[10px] uppercase font-bold tracking-widest shadow-[0_0_10px_currentColor] ${LABEL_COLORS[response.label]}`}>
              {response.label} MATCH
            </span>
          )}
        </div>
      </div>

      <div className="container-app py-8">
        {!assetId && (
          <div className="glass-panel rounded-2xl h-[400px] flex flex-col items-center justify-center py-24 gap-6 text-slate-600 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-50" />
            
            <div className="w-20 h-20 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center shadow-inner relative">
               <div className="absolute inset-0 rounded-full border border-cyan-500/30 animate-ping opacity-20" />
               <GitCompareArrows className="w-10 h-10 text-slate-500" />
            </div>
            
            <div className="text-center">
              <p className="text-white font-bold tracking-widest uppercase mb-2 text-lg">No Reference Target</p>
              <p className="text-slate-500 text-xs uppercase tracking-widest">Execute a semantic search first to acquire a target for correlation.</p>
            </div>
            <button onClick={() => navigate('/search')}
              className="mt-4 px-6 py-3 bg-cyan-950/50 hover:bg-cyan-900 border border-cyan-500/30 hover:border-cyan-400 text-cyan-400 hover:text-cyan-300 rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all flex items-center gap-2 shadow-[0_0_15px_rgba(6,182,212,0.1)] hover:shadow-[0_0_20px_rgba(6,182,212,0.3)]">
              <SearchIcon className="w-4 h-4" />
              Initialize Discovery
            </button>
          </div>
        )}

        {loading && (
          <div className="glass-panel rounded-2xl h-[400px] flex flex-col items-center justify-center gap-4 text-cyan-500">
            <Loader2 className="w-10 h-10 animate-spin" />
            <span className="text-xs font-bold uppercase tracking-widest animate-pulse">Running Correlation Matrix...</span>
          </div>
        )}

        {error && (
          <div className="flex items-start gap-3 p-4 bg-rose-950/40 border border-rose-500/30 rounded-xl text-rose-400 text-xs mb-6 shadow-inner">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex flex-col gap-1">
               <span className="font-bold uppercase tracking-widest">Correlation Failed</span>
               <span className="opacity-80">{error}</span>
            </div>
          </div>
        )}

        {response && !loading && (
          <div className="flex flex-col gap-6">
            <div className="flex items-center gap-2 px-1">
              <span className="text-cyan-400 font-bold uppercase tracking-widest text-xs flex items-center gap-2">
                 <Database className="w-4 h-4" />
                 {response.total} Vector Matches Found
              </span>
            </div>

            <div className="grid lg:grid-cols-5 gap-6">
              {/* Telemetry Map */}
              <div className="lg:col-span-2 glass-panel rounded-2xl overflow-hidden h-72 lg:h-auto lg:min-h-[500px] relative border border-slate-700">
                <div className="absolute top-4 left-4 z-[400] pointer-events-none">
                   <div className="bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded border border-slate-700 shadow-lg text-[10px] uppercase font-bold text-cyan-400 tracking-widest flex items-center gap-2">
                      <MapPin className="w-3 h-3" /> Spatial Distribution
                   </div>
                </div>
                <div className="map-tiles-dark w-full h-full">
                  <MapContainer center={[20.5937, 78.9629]} zoom={4} className="w-full h-full" zoomControl={false}>
                    <TileLayer
                      url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                      attribution="(c) Esri"
                    />
                    <MapFly results={mapResults} />
                    {mapResults.map((r, i) => (
                      <Marker key={r.asset_id} position={[(r.bbox[1] + r.bbox[3]) / 2, (r.bbox[0] + r.bbox[2]) / 2]}>
                        <Popup className="dark-popup">
                          <div className="min-w-[160px] p-1 font-mono">
                            <p className="font-bold text-xs uppercase text-cyan-400 tracking-wider border-b border-slate-700 pb-1 mb-1 truncate">{r.source}</p>
                            <div className="flex flex-col gap-1 text-[10px] text-slate-400 uppercase tracking-widest">
                               <span className="flex justify-between"><span>Sensor</span> <span className="text-white">{r.sensor}</span></span>
                               <span className="flex justify-between"><span>Date</span> <span className="text-white">{r.acquisition_time.slice(0, 10)}</span></span>
                               <span className="flex justify-between mt-1 pt-1 border-t border-slate-700">
                                  <span className="text-emerald-400">Match</span>
                                  <span className="text-emerald-400 font-bold">{(r.similarity_score * 100).toFixed(1)}%</span>
                               </span>
                            </div>
                          </div>
                        </Popup>
                      </Marker>
                    ))}
                  </MapContainer>
                </div>
              </div>

              {/* Vector Results Grid */}
              <div className="lg:col-span-3">
                {response.results.length === 0 ? (
                  <div className="glass-panel rounded-2xl h-full flex flex-col items-center justify-center py-16 gap-4 text-slate-600">
                    <GitCompareArrows className="w-12 h-12 opacity-30" />
                    <p className="text-xs font-bold uppercase tracking-widest text-center px-8">No vector matches found.<br/><span className="text-[10px] text-slate-500 mt-2 block">Ingest more telemetry data via the Data module.</span></p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                    {response.results.map((result, idx) => (
                      <motion.div
                        key={result.asset_id}
                        initial={{ opacity: 0, scale: 0.95, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        transition={{ delay: idx * 0.05 }}
                        onClick={() => setSelected(result)}
                        className={`glass-panel rounded-xl overflow-hidden cursor-pointer transition-all duration-300 relative group ${
                          selected?.asset_id === result.asset_id
                            ? 'border-cyan-500 shadow-[0_0_15px_rgba(6,182,212,0.3)] bg-cyan-900/20'
                            : 'border-slate-800 hover:border-cyan-500/50 hover:shadow-[0_0_15px_rgba(6,182,212,0.1)]'
                        }`}
                      >
                        {/* Rank Badge */}
                        <div className="absolute top-2 left-2 z-10 w-5 h-5 rounded bg-slate-900/80 backdrop-blur border border-slate-700 flex items-center justify-center text-[8px] font-bold text-slate-400 font-mono">
                           {(idx + 1).toString().padStart(2, '0')}
                        </div>

                        <div className="aspect-video bg-slate-950 relative overflow-hidden">
                          {result.thumbnail_b64 ? (
                            <img src={`data:image/jpeg;base64,${result.thumbnail_b64}`} alt={result.source} className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity group-hover:scale-105 duration-500" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-slate-700">
                              <Satellite className="w-6 h-6" />
                            </div>
                          )}
                          
                          {/* Match Score */}
                          <div className="absolute top-2 right-2 flex items-center gap-1.5 px-2 py-1 bg-slate-900/80 backdrop-blur border border-cyan-900/50 rounded shadow-md text-cyan-400 text-[10px] font-bold tracking-widest">
                            <Star className="w-3 h-3" />
                            {(result.similarity_score * 100).toFixed(1)}%
                          </div>
                        </div>
                        
                        <div className="p-3 bg-slate-900/60 border-t border-slate-800">
                          <p className="text-[11px] font-bold text-white truncate uppercase tracking-widest mb-1.5" title={result.source}>{result.source}</p>
                          <div className="flex flex-col gap-0.5 text-[9px] text-slate-500 uppercase tracking-widest mb-3 font-mono">
                             <span className="flex items-center gap-1.5"><Satellite className="w-2.5 h-2.5" /> {result.sensor}</span>
                             <span className="flex items-center gap-1.5"><Activity className="w-2.5 h-2.5" /> {result.acquisition_time.slice(0, 10)}</span>
                          </div>
                          
                          <button
                            onClick={(e) => { e.stopPropagation(); navigate(`/analyze/${result.asset_id}`) }}
                            className="w-full py-1.5 text-[10px] uppercase font-bold tracking-widest bg-cyan-950/40 text-cyan-400 border border-cyan-900 rounded hover:bg-cyan-900 hover:text-white transition-colors flex items-center justify-center gap-2"
                          >
                            <BarChart2 className="w-3 h-3" />
                            Execute Analysis
                          </button>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  )
}
