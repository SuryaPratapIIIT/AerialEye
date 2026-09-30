import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import {
  Upload, Image as ImageIcon, FileImage, X, Layers,
  Sparkles, ZoomIn, ZoomOut, Eye, EyeOff,
  Maximize2, Minimize2, Download, Check, MapPin, ArrowLeft,
  Activity, Terminal, Crosshair
} from 'lucide-react'
import LoadingOverlay from '../components/LoadingOverlay'
import { saveLatestAnalysis } from '../lib/analysis-storage'
import { analyzeSpatialImage, analyzeSpatialVideo, exportGeoJSON, exportCSV, type AnalysisMode } from '../utils/api'
import type { AnalysisApiSuccess, DetectedAsset, NormalizedPoint } from '../types/analysis'

type ViewMode = 'upload' | 'results'
type LayerInfo = AnalysisApiSuccess['transformed']['chart_data']['category_comparison_data'][number]
type OverlayShape = 'box' | 'polygon' | 'line'

interface DisplayPoint {
  x: number
  y: number
  isVisible: boolean
}

interface DisplayAsset {
  asset: DetectedAsset
  layer: LayerInfo
  shape: OverlayShape
  center: DisplayPoint
  bboxCorners: DisplayPoint[]
  polygon: DisplayPoint[]
  line: DisplayPoint[]
}

const TARGET_ASPECT_RATIO = 4 / 3
const ANALYSIS_MODE_LABELS: Record<AnalysisMode, string> = {
  block_analysis: 'Block Analysis',
  naming_analysis: 'Naming Analysis',
  asset_map_analysis: 'Asset Map',
  video_analysis: 'Video Analysis',
}

const VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.mpeg', '.mpg', '.m4v'] as const
const IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'] as const

function hasAnyExtension(filename: string, extensions: readonly string[]): boolean {
  const lower = filename.toLowerCase()
  return extensions.some((ext) => lower.endsWith(ext))
}

function isVideoFile(file: File | null): boolean {
  if (!file) return false
  if (file.type.startsWith('video/')) return true
  return hasAnyExtension(file.name, VIDEO_EXTENSIONS)
}

function isImageFile(file: File | null): boolean {
  if (!file) return false
  if (file.type.startsWith('image/')) return true
  return hasAnyExtension(file.name, IMAGE_EXTENSIONS)
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0
  if (value < 0) return 0
  if (value > 100) return 100
  return value
}

function isFinitePoint(point: NormalizedPoint | null | undefined): point is NormalizedPoint {
  return Boolean(point && Number.isFinite(point.x) && Number.isFinite(point.y))
}

function getCenterFromAsset(asset: DetectedAsset): NormalizedPoint {
  if (isFinitePoint(asset.center_coordinates)) {
    return {
      x: clampPercent(asset.center_coordinates.x),
      y: clampPercent(asset.center_coordinates.y),
    }
  }
  return {
    x: clampPercent((asset.bounding_box.x_min + asset.bounding_box.x_max) / 2),
    y: clampPercent((asset.bounding_box.y_min + asset.bounding_box.y_max) / 2),
  }
}

function getPolygonFromAsset(asset: DetectedAsset): NormalizedPoint[] {
  const points = (asset.polygon_coordinates || []).filter(isFinitePoint).map((point) => ({
    x: clampPercent(point.x),
    y: clampPercent(point.y),
  }))
  if (points.length >= 3) return points

  return [
    { x: clampPercent(asset.bounding_box.x_min), y: clampPercent(asset.bounding_box.y_min) },
    { x: clampPercent(asset.bounding_box.x_max), y: clampPercent(asset.bounding_box.y_min) },
    { x: clampPercent(asset.bounding_box.x_max), y: clampPercent(asset.bounding_box.y_max) },
    { x: clampPercent(asset.bounding_box.x_min), y: clampPercent(asset.bounding_box.y_max) },
  ]
}

function getBboxCorners(asset: DetectedAsset): NormalizedPoint[] {
  return [
    { x: clampPercent(asset.bounding_box.x_min), y: clampPercent(asset.bounding_box.y_min) },
    { x: clampPercent(asset.bounding_box.x_max), y: clampPercent(asset.bounding_box.y_min) },
    { x: clampPercent(asset.bounding_box.x_max), y: clampPercent(asset.bounding_box.y_max) },
    { x: clampPercent(asset.bounding_box.x_min), y: clampPercent(asset.bounding_box.y_max) },
  ]
}

function getRoadLine(asset: DetectedAsset): NormalizedPoint[] {
  const polygon = getPolygonFromAsset(asset)
  if (polygon.length >= 2) return polygon

  const width = Math.abs(asset.bounding_box.x_max - asset.bounding_box.x_min)
  const height = Math.abs(asset.bounding_box.y_max - asset.bounding_box.y_min)
  if (width >= height) {
    const yMid = clampPercent((asset.bounding_box.y_min + asset.bounding_box.y_max) / 2)
    return [
      { x: clampPercent(asset.bounding_box.x_min), y: yMid },
      { x: clampPercent(asset.bounding_box.x_max), y: yMid },
    ]
  }

  const xMid = clampPercent((asset.bounding_box.x_min + asset.bounding_box.x_max) / 2)
  return [
    { x: xMid, y: clampPercent(asset.bounding_box.y_min) },
    { x: xMid, y: clampPercent(asset.bounding_box.y_max) },
  ]
}

function getShapeForLayer(layerId: string): OverlayShape {
  if (layerId === 'roads' || layerId === 'drains') return 'line'
  if (layerId === 'green_cover' || layerId === 'parks' || layerId === 'water') return 'polygon'
  return 'box'
}

function getRenderableLayers(result: AnalysisApiSuccess): LayerInfo[] {
  const allLayers = result.transformed.chart_data.category_comparison_data || []
  const presentCategories = new Set(result.data.detected_assets.map((asset) => asset.category))
  return allLayers.filter((layer) => presentCategories.has(layer.category))
}

function pointsToString(points: DisplayPoint[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(' ')
}

function formatAreaSqM(area: number): string {
  if (!Number.isFinite(area) || area <= 0) return '0'
  return area.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

function formatHeightM(height: number): string {
  if (!Number.isFinite(height) || height <= 0) return '0.0'
  return height.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
}

export default function Detect() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('upload')
  const [analysisResult, setAnalysisResult] = useState<AnalysisApiSuccess | null>(null)
  const [enabledLayers, setEnabledLayers] = useState<string[]>([])
  const [showOriginal, setShowOriginal] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [layerMenuOpen, setLayerMenuOpen] = useState(false)
  const [hoveredAssetId, setHoveredAssetId] = useState<string | null>(null)
  const [exportingGeoJSON, setExportingGeoJSON] = useState(false)
  const [exportingCSV, setExportingCSV] = useState(false)
  const [imageNaturalSize, setImageNaturalSize] = useState<{ width: number; height: number } | null>(null)
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('block_analysis')
  const [modeVisualizationUrl, setModeVisualizationUrl] = useState<string | null>(null)
  const [modeVideoUrl, setModeVideoUrl] = useState<string | null>(null)

  const layerMenuRef = useRef<HTMLDivElement>(null)
  const fullscreenRef = useRef<HTMLDivElement>(null)
  const objectUrlRef = useRef<string | null>(null)

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (layerMenuRef.current && !layerMenuRef.current.contains(e.target as Node)) {
        setLayerMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  useEffect(() => {
    const h = () => setIsFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', h)
    return () => document.removeEventListener('fullscreenchange', h)
  }, [])

  useEffect(
    () => () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current)
      }
    },
    [],
  )

  const comparisonData = useMemo(
    () => (analysisResult ? getRenderableLayers(analysisResult) : []),
    [analysisResult],
  )

  const layerByCategory = useMemo(() => {
    const map = new Map<string, LayerInfo>()
    comparisonData.forEach((layer) => map.set(layer.category, layer))
    return map
  }, [comparisonData])

  const allAssets = analysisResult?.data.detected_assets || []
  const isVideoAnalysisMode = analysisMode === 'video_analysis'

  const visibleAssets = useMemo(
    () =>
      allAssets.filter((asset) => {
        const layer = layerByCategory.get(asset.category)
        return Boolean(layer && enabledLayers.includes(layer.layer_id))
      }),
    [allAssets, enabledLayers, layerByCategory],
  )

  const mapPointToViewport = useCallback(
    (point: NormalizedPoint): DisplayPoint => {
      const sourceX = clampPercent(point.x) / 100
      const sourceY = clampPercent(point.y) / 100

      if (!imageNaturalSize || imageNaturalSize.width <= 0 || imageNaturalSize.height <= 0) {
        return { x: sourceX * 100, y: sourceY * 100, isVisible: true }
      }

      const sourceAspect = imageNaturalSize.width / imageNaturalSize.height
      let mappedX = sourceX
      let mappedY = sourceY

      if (sourceAspect > TARGET_ASPECT_RATIO) {
        const scaledWidth = sourceAspect / TARGET_ASPECT_RATIO
        const cropLeft = (scaledWidth - 1) / 2
        mappedX = sourceX * scaledWidth - cropLeft
      } else if (sourceAspect < TARGET_ASPECT_RATIO) {
        const scaledHeight = TARGET_ASPECT_RATIO / sourceAspect
        const cropTop = (scaledHeight - 1) / 2
        mappedY = sourceY * scaledHeight - cropTop
      }

      return {
        x: mappedX * 100,
        y: mappedY * 100,
        isVisible: mappedX >= 0 && mappedX <= 1 && mappedY >= 0 && mappedY <= 1,
      }
    },
    [imageNaturalSize],
  )

  const displayAssets = useMemo<DisplayAsset[]>(
    () =>
      visibleAssets
        .map((asset) => {
          const layer = layerByCategory.get(asset.category)
          if (!layer) return null

          const shape = getShapeForLayer(layer.layer_id)
          const center = mapPointToViewport(getCenterFromAsset(asset))
          const bboxCorners = getBboxCorners(asset).map(mapPointToViewport)
          const polygon = getPolygonFromAsset(asset).map(mapPointToViewport)
          const line = getRoadLine(asset).map(mapPointToViewport)

          const hasVisibleGeometry =
            center.isVisible ||
            bboxCorners.some((point) => point.isVisible) ||
            polygon.some((point) => point.isVisible) ||
            line.some((point) => point.isVisible)
          if (!hasVisibleGeometry) return null

          return { asset, layer, shape, center, bboxCorners, polygon, line }
        })
        .filter((item): item is DisplayAsset => item !== null),
    [layerByCategory, mapPointToViewport, visibleAssets],
  )

  const areaCountSummary = useMemo(() => {
    const rows = comparisonData
      .map((layer) => ({
        layerId: layer.layer_id,
        category: layer.category,
        color: layer.color,
        count: Number.isFinite(layer.count) ? layer.count : 0,
        areaSqM: Number.isFinite(layer.area_sq_m) ? layer.area_sq_m : 0,
      }))
      .sort((a, b) => b.count - a.count)

    const totalCount = rows.reduce((sum, row) => sum + row.count, 0)
    const totalAreaSqM = rows.reduce((sum, row) => sum + row.areaSqM, 0)

    return { rows, totalCount, totalAreaSqM }
  }, [comparisonData])

  const buildingHeightSummary = useMemo(() => {
    const heights = allAssets
      .filter((asset) => String(asset.category || '').toLowerCase().includes('building'))
      .map((asset) => Number(asset.estimated_height_meters))
      .filter((value) => Number.isFinite(value) && value > 0)

    if (heights.length === 0) return null

    const total = heights.reduce((sum, value) => sum + value, 0)
    const avg = total / heights.length
    const min = Math.min(...heights)
    const max = Math.max(...heights)
    return { count: heights.length, avg, min, max }
  }, [allAssets])

  const mappedCount = isVideoAnalysisMode
    ? (analysisResult?.transformed.analytics_cards.total_assets_detected || 0)
    : displayAssets.length

  const setPreviewFromFile = useCallback((file: File) => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    const next = URL.createObjectURL(file)
    objectUrlRef.current = next
    setPreviewUrl(next)
  }, [])

  const toggleFullscreen = async () => {
    if (!document.fullscreenElement) {
      await fullscreenRef.current?.requestFullscreen()
    } else {
      await document.exitFullscreen()
    }
  }

  const onDrop = useCallback(
    (files: File[]) => {
      const f = files[0]
      if (!f) return
      setSelectedFile(f)
      setAnalysisMode(isVideoFile(f) ? 'video_analysis' : 'block_analysis')
      setPreviewFromFile(f)
      setAnalysisResult(null)
      setEnabledLayers([])
      setHoveredAssetId(null)
      setImageNaturalSize(null)
      setModeVisualizationUrl(null)
      setModeVideoUrl(null)
    },
    [setPreviewFromFile],
  )

  const dz = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'],
      'video/*': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.mpeg', '.mpg', '.m4v'],
    },
    maxSize: 500 * 1024 * 1024,
    multiple: false,
  })

  const clearSelection = () => {
    setSelectedFile(null)
    setAnalysisMode('block_analysis')
    setPreviewUrl(null)
    setAnalysisResult(null)
    setViewMode('upload')
    setEnabledLayers([])
    setHoveredAssetId(null)
    setImageNaturalSize(null)
    setModeVisualizationUrl(null)
    setModeVideoUrl(null)
  }

  const toggleLayer = (layerId: string) => {
    setEnabledLayers((prev) =>
      prev.includes(layerId) ? prev.filter((id) => id !== layerId) : [...prev, layerId],
    )
  }

  const handleExportGeoJSON = async () => {
    if (!analysisResult) return
    setExportingGeoJSON(true)
    try {
      const blob = await exportGeoJSON(analysisResult)
      const url = URL.createObjectURL(blob)
      Object.assign(document.createElement('a'), { href: url, download: 'detection_blocks.geojson' }).click()
      URL.revokeObjectURL(url)
    } finally {
      setTimeout(() => setExportingGeoJSON(false), 1500)
    }
  }

  const handleExportCSV = async () => {
    if (!analysisResult) return
    setExportingCSV(true)
    try {
      const blob = await exportCSV(analysisResult)
      const url = URL.createObjectURL(blob)
      Object.assign(document.createElement('a'), { href: url, download: 'detection_blocks.csv' }).click()
      URL.revokeObjectURL(url)
    } finally {
      setTimeout(() => setExportingCSV(false), 1500)
    }
  }

  const runDetection = async (mode: AnalysisMode) => {
    if (!selectedFile) return

    const selectedIsVideo = isVideoFile(selectedFile)
    const selectedIsImage = isImageFile(selectedFile)
    if (mode === 'video_analysis' && !selectedIsVideo) {
      alert('Please upload a video file for Video Analysis.')
      return
    }
    if (mode !== 'video_analysis' && !selectedIsImage) {
      alert('Please upload an image file for Block, Naming, or Asset Map analysis.')
      return
    }

    setAnalysisMode(mode)
    setIsProcessing(true)

    try {
      const result =
        mode === 'video_analysis'
          ? await analyzeSpatialVideo(selectedFile)
          : await analyzeSpatialImage(selectedFile, mode)
      if (!result.success) {
        alert(`Analysis Failed: ${result.error.message}\n${result.error.details || ''}`)
        return
      }

      let layers = getRenderableLayers(result).map((layer) => layer.layer_id)

      if (layers.length === 0) {
        const categoryToLayerId: Record<string, string> = {
          'Properties & Buildings': 'buildings',
          'Trees & Green Cover': 'green_cover',
          'Parks & Open Spaces': 'parks',
          'Water Bodies': 'water',
          'Roads & Footpaths': 'roads',
          'Drains & Sewage': 'drains',
          'Vehicles & Parking': 'vehicles',
          'Waste Dumps': 'waste',
          'Solar Panels': 'solar',
        }
        const uniqueCats = [...new Set(result.data.detected_assets.map((a) => a.category))]
        layers = uniqueCats.map((cat) => categoryToLayerId[cat] || 'buildings').filter(Boolean)
      }

      setAnalysisResult(result)
      setEnabledLayers([...new Set(layers)])
      setHoveredAssetId(null)
      setImageNaturalSize(null)
      setViewMode('results')
      setZoom(1)
      setShowOriginal(false)
      setModeVisualizationUrl(
        mode === 'naming_analysis' || mode === 'asset_map_analysis'
          ? result.height_visualization_data_url ||
            (mode === 'naming_analysis'
              ? result.naming_visualization_data_url || null
              : result.asset_map_visualization_data_url || null)
          : null,
      )
      setModeVideoUrl(mode === 'video_analysis' ? result.video_result_url || null : null)
      saveLatestAnalysis(result)
    } catch (err) {
      alert('An unexpected error occurred during analysis.')
      console.error(err)
    } finally {
      setIsProcessing(false)
    }
  }

  const handleResultImageLoad = (event: React.SyntheticEvent<HTMLImageElement>) => {
    const target = event.currentTarget
    if (target.naturalWidth > 0 && target.naturalHeight > 0) {
      setImageNaturalSize({ width: target.naturalWidth, height: target.naturalHeight })
    }
  }

  if (viewMode === 'upload') {
    return (
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="min-h-screen pt-20 pb-16 font-mono"
      >
        <LoadingOverlay isVisible={isProcessing} onComplete={() => {}} />
        
        <div className="container-app py-8 flex flex-col gap-8 max-w-5xl">
          <div className="flex flex-col items-center text-center gap-3 mb-10">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-cyan-900/30 text-cyan-400 text-xs font-semibold tracking-wide uppercase border border-cyan-500/30">
              <Crosshair className="w-3 h-3" /> Spatial Block Detection
            </span>
            <h1 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold text-white tracking-wide uppercase">
              ML Model Analysis
            </h1>
            <p className="text-slate-400 text-sm sm:text-base max-w-lg tracking-wider">
              Upload imagery to detect assets as perfectly mapped spatial blocks in real-time.
            </p>
          </div>

          {!selectedFile ? (
            <div className="glass-panel p-8 rounded-2xl h-[400px] flex flex-col items-center justify-center relative overflow-hidden">
               <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-cyan-500 to-transparent shadow-[0_0_10px_rgba(6,182,212,1)]" />
               <div
                 {...dz.getRootProps()}
                 className={`w-full max-w-2xl min-h-[250px] border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-300 relative group ${
                   dz.isDragActive ? 'border-cyan-500 bg-cyan-900/20 shadow-[inset_0_0_30px_rgba(6,182,212,0.2)]' : 'border-slate-700 hover:border-cyan-500/50 hover:bg-slate-800/50'
                 }`}
               >
                 <div className="absolute inset-0 bg-cyan-500/5 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                 <input {...dz.getInputProps()} />
                 <Upload className={`w-12 h-12 mb-4 transition-colors duration-300 ${dz.isDragActive ? 'text-cyan-400' : 'text-slate-600 group-hover:text-cyan-500/50'}`} />
                 <p className="text-white font-bold tracking-widest uppercase text-lg mb-2">
                   {dz.isDragActive ? 'Initiate Transfer' : 'Transmit Assets'}
                 </p>
                 <p className="text-slate-500 text-xs">Drop payload here or click to interface</p>
                 <p className="text-slate-600 text-[10px] uppercase tracking-widest mt-4">Formats: JPG, PNG, TIFF, WEBP, MP4, MOV // 500MB Max</p>
               </div>
            </div>
          ) : (
            <motion.div
              initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              className="glass-panel rounded-2xl overflow-hidden border border-slate-700 shadow-xl"
            >
              <div className="relative bg-slate-950 flex items-center justify-center">
                {isVideoFile(selectedFile) ? (
                  <video
                    src={previewUrl || ''}
                    className="w-full max-h-[420px] sm:max-h-[520px] object-contain"
                    controls
                    playsInline
                  />
                ) : (
                  <img
                    src={previewUrl || ''}
                    alt="Selected"
                    crossOrigin="anonymous"
                    className="w-full max-h-[420px] sm:max-h-[520px] object-contain"
                  />
                )}
                <button
                  onClick={clearSelection}
                  className="absolute top-4 right-4 w-10 h-10 rounded-xl bg-slate-900/80 backdrop-blur-md border border-slate-700 flex items-center justify-center text-slate-400 hover:text-white hover:border-cyan-500 hover:shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              
              <div className="p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6 border-t border-slate-800 bg-slate-900/50">
                <div className="flex items-center gap-4 min-w-0">
                  <div className="w-12 h-12 rounded-xl bg-cyan-900/30 border border-cyan-500/30 flex items-center justify-center shrink-0">
                    <FileImage className="w-6 h-6 text-cyan-400" />
                  </div>
                  <div className="min-w-0">
                    <p className="font-bold text-white text-sm truncate uppercase tracking-widest">{selectedFile.name}</p>
                    <p className="text-[10px] text-cyan-500 mt-1 uppercase tracking-widest flex items-center gap-2">
                       <Activity className="w-3 h-3" />
                       Ready for {ANALYSIS_MODE_LABELS[analysisMode]}
                    </p>
                  </div>
                </div>
                
                <div className="w-full sm:w-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  <button
                    onClick={() => void runDetection('block_analysis')}
                    className="w-full px-4 py-3 bg-cyan-950/50 hover:bg-cyan-900 border border-cyan-500/30 hover:border-cyan-400 text-cyan-400 hover:text-cyan-300 rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all inline-flex items-center justify-center gap-2 hover:shadow-[0_0_15px_rgba(6,182,212,0.3)]"
                  >
                    <ImageIcon className="w-3.5 h-3.5" /> Block Analysis
                  </button>
                  <button
                    onClick={() => void runDetection('naming_analysis')}
                    className="w-full px-4 py-3 bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-cyan-500/50 text-slate-300 hover:text-white rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all inline-flex items-center justify-center gap-2"
                  >
                    <Terminal className="w-3.5 h-3.5" /> Naming Analysis
                  </button>
                  <button
                    onClick={() => void runDetection('asset_map_analysis')}
                    className="w-full px-4 py-3 bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-cyan-500/50 text-slate-300 hover:text-white rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all inline-flex items-center justify-center gap-2"
                  >
                    <MapPin className="w-3.5 h-3.5" /> Asset Map
                  </button>
                  <button
                    onClick={() => void runDetection('video_analysis')}
                    className="w-full px-4 py-3 bg-slate-900 hover:bg-slate-800 border border-slate-700 hover:border-cyan-500/50 text-slate-300 hover:text-white rounded-xl font-bold text-[10px] uppercase tracking-widest transition-all inline-flex items-center justify-center gap-2"
                  >
                    <Activity className="w-3.5 h-3.5" /> Video Analysis
                  </button>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="bg-[#0a0d14] pt-14 h-screen flex flex-col font-mono"
    >
      <LoadingOverlay isVisible={isProcessing} onComplete={() => {}} />
      
      {/* Top Action Bar */}
      <div className="bg-slate-900/80 backdrop-blur-md border-b border-cyan-900/30 px-4 sm:px-6 py-3 flex items-center justify-between gap-3 shrink-0 shadow-[0_4px_30px_rgba(0,0,0,0.5)] z-40 relative">
        <div className="flex items-center gap-4">
          <button
            onClick={clearSelection}
            className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400 hover:text-cyan-400 transition-colors group bg-slate-800/50 px-3 py-1.5 rounded-lg border border-slate-700 hover:border-cyan-500/50"
          >
            <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-0.5 transition-transform" />
            <span className="hidden sm:inline">New Target</span>
          </button>
          
          <span className="hidden sm:block w-px h-6 bg-slate-700/50" />
          
          <div className="flex items-center gap-2 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
            <span className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.8)] animate-pulse" />
            <span className="text-sm font-bold text-white tracking-widest">
              {analysisResult?.transformed.analytics_cards.total_assets_detected || 0}
            </span>
            <span className="text-[10px] text-slate-500 uppercase tracking-widest">{isVideoAnalysisMode ? 'Detections' : 'Blocks'} Mapped</span>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={() => void runDetection('block_analysis')}
            disabled={!selectedFile || isProcessing}
            className={`hidden sm:inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-[10px] uppercase font-bold tracking-widest border transition-all ${
              analysisMode === 'block_analysis'
                ? 'bg-cyan-950/50 text-cyan-400 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-400 border-slate-700 hover:border-cyan-500/30'
            } ${!selectedFile || isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            Block Analysis
          </button>
          <button
            onClick={() => void runDetection('naming_analysis')}
            disabled={!selectedFile || isProcessing}
            className={`hidden sm:inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-[10px] uppercase font-bold tracking-widest border transition-all ${
              analysisMode === 'naming_analysis'
                ? 'bg-cyan-950/50 text-cyan-400 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-400 border-slate-700 hover:border-cyan-500/30'
            } ${!selectedFile || isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            Naming Analysis
          </button>
          <button
            onClick={() => void runDetection('asset_map_analysis')}
            disabled={!selectedFile || isProcessing}
            className={`hidden sm:inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-[10px] uppercase font-bold tracking-widest border transition-all ${
              analysisMode === 'asset_map_analysis'
                ? 'bg-cyan-950/50 text-cyan-400 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
                : 'bg-slate-900 hover:bg-slate-800 text-slate-400 border-slate-700 hover:border-cyan-500/30'
            } ${!selectedFile || isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            Asset Map
          </button>
          
          <span className="w-px h-6 bg-slate-700/50 mx-1" />

          <button
            onClick={handleExportGeoJSON}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white text-[10px] uppercase font-bold tracking-widest border border-slate-700 transition-colors"
          >
            {exportingGeoJSON ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Download className="w-3.5 h-3.5" />}
            {exportingGeoJSON ? 'Saved' : 'GeoJSON'}
          </button>
          <button
            onClick={handleExportCSV}
            className="hidden sm:inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white text-[10px] uppercase font-bold tracking-widest border border-slate-700 transition-colors"
          >
            {exportingCSV ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Download className="w-3.5 h-3.5" />}
            {exportingCSV ? 'Saved' : 'CSV'}
          </button>
        </div>
      </div>

      <div ref={fullscreenRef} className="flex-1 relative bg-slate-950 overflow-hidden">
        
        {/* Floating Controls Overlay */}
        <div className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between gap-4 pointer-events-none">
          <div className="pointer-events-auto flex items-center glass-panel rounded-xl overflow-hidden h-10 border border-slate-700 shadow-xl">
            <button
              onClick={() => setZoom((z) => Math.min(z + 0.25, 4))}
              className="h-full px-3 flex items-center text-slate-400 hover:text-cyan-400 hover:bg-slate-800 border-r border-slate-700 transition-colors"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <span className="px-4 text-xs font-bold text-cyan-500 tabular-nums bg-slate-900 h-full flex items-center justify-center tracking-widest">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom((z) => Math.max(z - 0.25, 0.5))}
              className="h-full px-3 flex items-center text-slate-400 hover:text-cyan-400 hover:bg-slate-800 border-l border-slate-700 transition-colors"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
          </div>

          <div className="pointer-events-auto flex items-center gap-2">
            <button
              onClick={() => setShowOriginal((value) => !value)}
              className={`h-10 px-4 rounded-xl inline-flex items-center gap-2 border text-[10px] font-bold uppercase tracking-widest transition-all duration-150 ${
                showOriginal
                  ? 'bg-cyan-950/80 text-cyan-400 border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.2)]'
                  : 'glass-panel text-slate-400 hover:text-white border-slate-700'
              }`}
            >
              {showOriginal ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
              <span className="hidden sm:inline">{showOriginal ? 'Base Image' : 'Overlay Mode'}</span>
            </button>

            <div className="relative" ref={layerMenuRef}>
              <button
                onClick={() => setLayerMenuOpen((value) => !value)}
                className={`h-10 px-4 rounded-xl inline-flex items-center gap-2 border text-[10px] font-bold uppercase tracking-widest transition-all duration-150 ${
                  layerMenuOpen
                    ? 'bg-cyan-950/80 text-cyan-400 border-cyan-500/50 shadow-[0_0_15px_rgba(6,182,212,0.2)]'
                    : 'glass-panel text-slate-400 hover:text-white border-slate-700'
                }`}
              >
                <Layers className="w-4 h-4" />
                <span className="hidden sm:inline">Data Layers</span>
                {!layerMenuOpen && (
                  <span className="ml-1 w-5 h-5 rounded bg-cyan-900/50 border border-cyan-500/30 text-cyan-400 text-[10px] font-bold inline-flex items-center justify-center">
                    {enabledLayers.length}
                  </span>
                )}
              </button>

              <AnimatePresence>
                {layerMenuOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: -6, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: -6, scale: 0.97 }}
                    transition={{ duration: 0.14, ease: 'easeOut' }}
                    className="absolute right-0 top-12 w-64 glass-panel rounded-xl shadow-2xl border border-slate-700 overflow-hidden z-30"
                  >
                    <div className="px-4 py-3 border-b border-slate-700/50 bg-slate-900/80 flex items-center justify-between">
                      <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-widest flex items-center gap-2">
                        <Terminal className="w-3.5 h-3.5" /> Toggle Overlay
                      </span>
                      <button onClick={() => setLayerMenuOpen(false)} className="text-slate-500 hover:text-white transition-colors">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <div className="p-2 flex flex-col gap-1 max-h-72 overflow-y-auto custom-scrollbar bg-slate-900/40">
                      {comparisonData.map((cls) => {
                        const on = enabledLayers.includes(cls.layer_id)
                        return (
                          <button
                            key={cls.layer_id}
                            onClick={() => toggleLayer(cls.layer_id)}
                            className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-left transition-all duration-150 ${
                              on ? 'bg-slate-800/80 hover:bg-slate-700 border border-slate-700' : 'opacity-60 hover:opacity-100 hover:bg-slate-800 border border-transparent'
                            }`}
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <span className="w-2.5 h-2.5 rounded-sm shrink-0 border border-white/20 shadow-[0_0_5px_currentColor]" style={{ backgroundColor: cls.color, color: cls.color }} />
                              <span className="text-[11px] font-bold text-white uppercase tracking-wider truncate">{cls.category}</span>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <span className="text-[10px] text-cyan-500/80 font-mono tabular-nums">{cls.count}</span>
                              <div className={`w-7 h-3.5 rounded-full p-[2px] transition-colors border ${on ? 'bg-cyan-900/80 border-cyan-500/50' : 'bg-slate-900 border-slate-700'}`}>
                                <motion.div
                                  className={`w-2.5 h-2.5 rounded-full shadow-[0_0_5px_currentColor] ${on ? 'bg-cyan-400 text-cyan-400' : 'bg-slate-500 text-transparent'}`}
                                  animate={{ x: on ? 14 : 0 }}
                                  transition={{ type: 'spring', stiffness: 600, damping: 35 }}
                                />
                              </div>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                    <div className="p-2 border-t border-slate-700/50 bg-slate-900/80 flex gap-2">
                      <button
                        onClick={() => setEnabledLayers(comparisonData.map((item) => item.layer_id))}
                        className="flex-1 py-1.5 rounded text-[10px] uppercase tracking-widest font-bold text-cyan-400 bg-cyan-950/50 hover:bg-cyan-900 border border-cyan-900 hover:border-cyan-500/50 transition-colors"
                      >
                        Enable All
                      </button>
                      <button
                        onClick={() => setEnabledLayers([])}
                        className="flex-1 py-1.5 rounded text-[10px] uppercase tracking-widest font-bold text-slate-400 bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:text-white transition-colors"
                      >
                        Disable All
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <button
              onClick={toggleFullscreen}
              className="w-10 h-10 glass-panel rounded-xl flex items-center justify-center text-slate-400 hover:text-cyan-400 shadow-xl border border-slate-700 transition-colors"
            >
              {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Viewport */}
        <div className="w-full h-full flex items-center justify-center overflow-auto p-6 pt-20 pb-12">
          <div
            className="relative shrink-0 border border-slate-800 shadow-[0_0_30px_rgba(0,0,0,0.8)] rounded-xl bg-black"
            style={{ transform: `scale(${zoom})`, transformOrigin: 'center', transition: 'transform 0.25s ease' }}
          >
            {isVideoAnalysisMode ? (
              <video
                src={!showOriginal && modeVideoUrl ? modeVideoUrl : (previewUrl || '')}
                className="block w-[min(760px,88vw)] aspect-[4/3] object-cover rounded-xl select-none bg-black"
                controls
                playsInline
              />
            ) : (
              <img
                src={
                  (analysisMode === 'naming_analysis' || analysisMode === 'asset_map_analysis') &&
                  !showOriginal &&
                  modeVisualizationUrl
                    ? modeVisualizationUrl
                    : (previewUrl || '')
                }
                alt="Detected imagery"
                crossOrigin="anonymous"
                className="block w-[min(760px,88vw)] aspect-[4/3] object-cover rounded-xl select-none"
                draggable={false}
                onLoad={handleResultImageLoad}
              />
            )}

            {!isVideoAnalysisMode &&
              !showOriginal &&
              !(
                (analysisMode === 'naming_analysis' || analysisMode === 'asset_map_analysis') &&
                modeVisualizationUrl
              ) && (
              <svg className="absolute inset-0 w-full h-full rounded-xl overflow-hidden pointer-events-auto" viewBox="0 0 100 100" preserveAspectRatio="none">
                {displayAssets.map(({ asset, layer, shape, center, bboxCorners, polygon, line }) => {
                  const color = layer.color || '#888'
                  const isHovered = hoveredAssetId === asset.unique_id
                  const minX = Math.min(...bboxCorners.map((point) => point.x))
                  const maxX = Math.max(...bboxCorners.map((point) => point.x))
                  const minY = Math.min(...bboxCorners.map((point) => point.y))
                  const maxY = Math.max(...bboxCorners.map((point) => point.y))
                  const width = Math.max(maxX - minX, 0.45)
                  const height = Math.max(maxY - minY, 0.45)

                  if (analysisMode === 'naming_analysis') {
                    const labelClass = (asset.subcategory || 'unknown')
                      .trim()
                      .toLowerCase()
                      .replace(/\s+/g, '_')
                    const confidenceScore = Math.max(
                      0,
                      Math.min(asset.confidence_percent / 100, 1),
                    )
                    const label = `${labelClass} ${confidenceScore.toFixed(2)}`
                    const labelWidth = Math.min(98, Math.max(14, label.length * 1.65))
                    const labelHeight = 5.2
                    const labelX = Math.max(0.4, Math.min(minX, 99.6 - labelWidth))
                    const labelY =
                      minY > 6
                        ? minY - labelHeight
                        : Math.max(0.4, Math.min(maxY + 0.5, 99.6 - labelHeight))

                    return (
                      <g
                        key={asset.unique_id}
                        onMouseEnter={() => setHoveredAssetId(asset.unique_id)}
                        onMouseLeave={() => setHoveredAssetId(null)}
                        className="cursor-pointer"
                      >
                        <rect
                          x={minX}
                          y={minY}
                          width={width}
                          height={height}
                          fill="none"
                          stroke="#06b6d4" // cyan-500
                          strokeWidth={isHovered ? 0.75 : 0.55}
                          vectorEffect="non-scaling-stroke"
                        />
                        <rect
                          x={labelX}
                          y={labelY}
                          width={labelWidth}
                          height={labelHeight}
                          fill="#083344" // cyan-950
                          stroke="#06b6d4"
                          strokeWidth={0.2}
                          vectorEffect="non-scaling-stroke"
                        />
                        <text
                          x={labelX + 0.9}
                          y={labelY + 3.65}
                          fill="#22d3ee" // cyan-400
                          fontSize={3.9}
                          fontWeight={700}
                          fontFamily="monospace"
                        >
                          {label}
                        </text>
                      </g>
                    )
                  }

                  if (shape === 'line') {
                    const strokeWidth = layer.layer_id === 'roads' ? (isHovered ? 1.1 : 0.8) : (isHovered ? 0.65 : 0.38)
                    const dash = layer.layer_id === 'drains' ? '0.9 0.7' : undefined
                    const strokeColor = color
                    const strokeOpacity = layer.layer_id === 'roads' ? 1 : 0.95
                    return (
                      <g
                        key={asset.unique_id}
                        onMouseEnter={() => setHoveredAssetId(asset.unique_id)}
                        onMouseLeave={() => setHoveredAssetId(null)}
                        className="cursor-pointer drop-shadow-md"
                      >
                          <polyline
                          points={pointsToString(line)}
                          fill="none"
                          stroke={strokeColor}
                          strokeOpacity={strokeOpacity}
                          strokeWidth={strokeWidth}
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeDasharray={dash}
                          vectorEffect="non-scaling-stroke"
                        />
                      </g>
                    )
                  }

                  if (shape === 'polygon') {
                    return (
                      <g
                        key={asset.unique_id}
                        onMouseEnter={() => setHoveredAssetId(asset.unique_id)}
                        onMouseLeave={() => setHoveredAssetId(null)}
                        className="cursor-pointer"
                      >
                        <polygon
                          points={pointsToString(polygon)}
                          fill={color}
                          fillOpacity={isHovered ? 0.5 : 0.2}
                          stroke={color}
                          strokeOpacity={0.95}
                          strokeWidth={isHovered ? 0.6 : 0.34}
                          strokeDasharray="0.8 0.6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          vectorEffect="non-scaling-stroke"
                        />
                        <circle
                          cx={center.x}
                          cy={center.y}
                          r={isHovered ? 0.7 : 0.5}
                          fill={color}
                          fillOpacity={0.9}
                          stroke="#fff"
                          strokeWidth={0.22}
                          vectorEffect="non-scaling-stroke"
                        />
                      </g>
                    )
                  }

                  const shrink = 0.72
                  const drawWidth = Math.max(width * shrink, 0.35)
                  const drawHeight = Math.max(height * shrink, 0.35)
                  const drawX = minX + (width - drawWidth) / 2
                  const drawY = minY + (height - drawHeight) / 2

                  return (
                    <g
                      key={asset.unique_id}
                      onMouseEnter={() => setHoveredAssetId(asset.unique_id)}
                      onMouseLeave={() => setHoveredAssetId(null)}
                      className="cursor-pointer"
                    >
                      <rect
                        x={drawX}
                        y={drawY}
                        width={drawWidth}
                        height={drawHeight}
                        rx={0.35}
                        ry={0.35}
                        fill={color}
                        fillOpacity={isHovered ? 0.5 : 0.24}
                        stroke={color}
                        strokeOpacity={0.95}
                        strokeWidth={isHovered ? 0.65 : 0.35}
                        vectorEffect="non-scaling-stroke"
                      />
                    </g>
                  )
                })}
              </svg>
            )}
          </div>

          <AnimatePresence>
            {hoveredAssetId !== null && (() => {
              const asset = allAssets.find((item) => item.unique_id === hoveredAssetId)
              const layer = asset ? layerByCategory.get(asset.category) : null
              return asset && layer ? (
                <motion.div
                  initial={{ opacity: 0, y: 6, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 6, scale: 0.95 }}
                  className="absolute bottom-16 right-6 glass-panel rounded-xl p-4 shadow-2xl border border-slate-700 z-10 w-[260px] pointer-events-none"
                >
                  <div className="flex items-center gap-3 mb-3 pb-3 border-b border-slate-700/50">
                    <span className="w-3 h-3 rounded-[2px] shrink-0 shadow-[0_0_8px_currentColor]" style={{ backgroundColor: layer.color, color: layer.color }} />
                    <span className="font-bold text-white text-[11px] uppercase tracking-widest leading-tight">{asset.category}</span>
                  </div>
                  <div className="space-y-2">
                    <div className="flex justify-between items-center text-[10px] uppercase tracking-widest">
                      <span className="text-slate-500 font-bold">Subtype</span>
                      <span className="font-bold text-cyan-400 bg-cyan-950/50 px-1.5 py-0.5 rounded border border-cyan-900">{asset.subcategory}</span>
                    </div>
                    <div className="flex justify-between items-center text-[10px] uppercase tracking-widest">
                      <span className="text-slate-500 font-bold">Confidence</span>
                      <span className="font-bold text-emerald-400">{asset.confidence_percent.toFixed(1)}%</span>
                    </div>
                    <div className="flex justify-between items-center text-[10px] uppercase tracking-widest">
                      <span className="text-slate-500 font-bold">Est. Area</span>
                      <span className="font-bold text-amber-400">{asset.estimated_area_sq_m} m²</span>
                    </div>
                    {Number.isFinite(asset.estimated_height_meters) && (asset.estimated_height_meters || 0) > 0 && (
                      <div className="flex justify-between items-center text-[10px] uppercase tracking-widest">
                        <span className="text-slate-500 font-bold">Height</span>
                        <span className="font-bold text-violet-400">{asset.estimated_height_meters?.toFixed(1)} m</span>
                      </div>
                    )}
                  </div>
                  {asset.visual_description && (
                    <p className="mt-3 text-[10px] text-slate-400 leading-snug border-t border-slate-700/50 pt-3 italic opacity-80">
                      "{asset.visual_description}"
                    </p>
                  )}
                </motion.div>
              ) : null
            })()}
          </AnimatePresence>
        </div>

        {/* Bottom Left HUD (Coordinates) */}
        <div className="absolute bottom-4 left-4 glass-panel rounded-xl px-4 h-10 flex items-center gap-4 shadow-xl border border-slate-700 pointer-events-none">
          <span className="flex items-center gap-2 text-cyan-400 text-[10px] font-bold uppercase tracking-widest">
            <MapPin className="w-3.5 h-3.5" />
            {analysisResult?.transformed.gis_mapping.map_center.lat.toFixed(4)}°N,{' '}
            {analysisResult?.transformed.gis_mapping.map_center.lng.toFixed(4)}°E
          </span>
          <span className="w-px h-5 bg-slate-700" />
          <span className="text-emerald-400 text-[10px] font-bold uppercase tracking-widest">
            {mappedCount} {isVideoAnalysisMode ? 'detections' : 'blocks'} mapped
          </span>
          <span className="w-px h-5 bg-slate-700" />
          <span className="text-slate-400 text-[10px] font-bold uppercase tracking-widest">
            Avg height: {buildingHeightSummary ? <span className="text-white">{formatHeightM(buildingHeightSummary.avg)} m</span> : 'N/A'}
          </span>
        </div>

        {/* Bottom Right HUD (Telemetry List) */}
        <div className="absolute bottom-4 right-4 glass-panel rounded-xl p-3 shadow-xl border border-slate-700 hidden sm:flex flex-col gap-2 max-h-64 overflow-y-auto custom-scrollbar min-w-[320px] pointer-events-auto">
          <div className="border-b border-cyan-900/50 pb-2 mb-1">
            <p className="text-[10px] font-bold uppercase tracking-widest text-cyan-500 flex items-center gap-1.5 mb-2">
               <Activity className="w-3 h-3" /> Area Distribution
            </p>
            <div className="flex items-center justify-between mt-1 text-[10px] uppercase font-bold tracking-widest">
              <span className="text-slate-500">Total objects</span>
              <span className="text-cyan-400">{areaCountSummary.totalCount}</span>
            </div>
            <div className="flex items-center justify-between mt-1 text-[10px] uppercase font-bold tracking-widest">
              <span className="text-slate-500">Total area</span>
              <span className="text-cyan-400">
                {formatAreaSqM(areaCountSummary.totalAreaSqM)} m²
              </span>
            </div>
            <div className="flex items-center justify-between mt-1 text-[10px] uppercase font-bold tracking-widest">
              <span className="text-slate-500">Height (avg|min|max)</span>
              <span className="text-cyan-400">
                {buildingHeightSummary
                  ? `${formatHeightM(buildingHeightSummary.avg)} | ${formatHeightM(buildingHeightSummary.min)} | ${formatHeightM(buildingHeightSummary.max)} m`
                  : 'N/A'}
              </span>
            </div>
          </div>

          {areaCountSummary.rows.length > 0 ? (
            areaCountSummary.rows.map((row) => (
              <div key={row.layerId} className="flex items-center gap-3 py-1">
                <span
                  className="w-2.5 h-2.5 rounded-[2px] shrink-0 shadow-[0_0_5px_currentColor]"
                  style={{ backgroundColor: row.color, color: row.color }}
                />
                <span className="text-[10px] text-white font-bold uppercase tracking-widest truncate max-w-[120px]">{row.category}</span>
                <div className="ml-auto pl-2 flex items-center gap-3">
                  <span className="text-[10px] text-slate-500 font-bold tabular-nums">{row.count} obj</span>
                  <span className="text-[10px] text-slate-400 font-bold tabular-nums w-16 text-right">{formatAreaSqM(row.areaSqM)} m²</span>
                </div>
              </div>
            ))
          ) : (
            <div className="text-[10px] text-slate-500 font-bold uppercase tracking-widest text-center py-2">System Idle</div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
