import type {
  AnalysisApiError,
  AnalysisApiResponse,
  AnalysisApiSuccess,
  LeafletPolygon,
  SearchResponse,
  SceneResult,
  ObservationsResponse,
  ChangeAnalysisResult,
  ReviewQueue,
  DataStatus,
  IngestResult,
} from '../types/analysis'

const REQUEST_TIMEOUT_MS = 180_000
const VIDEO_REQUEST_TIMEOUT_MS = 900_000
export type AnalysisMode = 'block_analysis' | 'naming_analysis' | 'asset_map_analysis' | 'video_analysis'

function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_ANALYSIS_API_BASE as string | undefined
  return (configured && configured.trim()) || 'http://localhost:8000'
}

function buildEndpoint(base: string, path: string): string {
  const trimmed = base.replace(/\/+$/, '')
  return `${trimmed}${path}`
}

function resolveCandidateEndpoints(path: string): string[] {
  const configuredBase = getApiBaseUrl()
  const endpoints: string[] = []
  if (configuredBase) {
    endpoints.push(buildEndpoint(configuredBase, path))
    if (configuredBase.includes('localhost')) {
      endpoints.push(buildEndpoint(configuredBase.replace('localhost', '127.0.0.1'), path))
    } else if (configuredBase.includes('127.0.0.1')) {
      endpoints.push(buildEndpoint(configuredBase.replace('127.0.0.1', 'localhost'), path))
    }
  } else {
    endpoints.push(`http://localhost:8000${path}`)
    endpoints.push(`http://127.0.0.1:8000${path}`)
  }
  return [...new Set(endpoints)]
}

function getBase(): string {
  return getApiBaseUrl()
}

function toErrorPayload(message: string, details = '', code = 'request_failed'): AnalysisApiError {
  return { success: false, error: { code, message, details } }
}

// -----------------------------------------------------------------------
// Generic fetch helpers
// -----------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  const url = `${getBase()}${path}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, { ...init, signal: controller.signal })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`HTTP ${res.status}: ${body.slice(0, 300)}`)
    }
    return res.json() as Promise<T>
  } finally {
    clearTimeout(timer)
  }
}

// -----------------------------------------------------------------------
// Health
// -----------------------------------------------------------------------

export async function pingBackendHealth(): Promise<boolean> {
  const endpoints = resolveCandidateEndpoints('/api/health')
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, { method: 'GET' })
      if (response.ok) return true
    } catch { /* ignore */ }
  }
  return false
}

// -----------------------------------------------------------------------
// Legacy analysis endpoints (preserved)
// -----------------------------------------------------------------------

function buildAnalysisForm(imageFile: File, analysisMode: AnalysisMode): FormData {
  const form = new FormData()
  form.append('image', imageFile)
  form.append('analysis_mode', analysisMode)
  return form
}

function buildVideoForm(videoFile: File): FormData {
  const form = new FormData()
  form.append('video', videoFile)
  return form
}

function isAnalysisSuccess(payload: unknown): payload is AnalysisApiSuccess {
  if (!payload || typeof payload !== 'object') return false
  const typed = payload as AnalysisApiSuccess
  return Boolean(
    typed.success === true &&
      typed.request_id &&
      typed.data &&
      typed.transformed &&
      Array.isArray(typed.data.detected_assets) &&
      Array.isArray(typed.warnings),
  )
}

async function parseErrorResponse(response: Response): Promise<AnalysisApiError> {
  try {
    const payload = await response.json()
    if (payload?.detail?.success === false && payload.detail.error) return payload.detail as AnalysisApiError
    if (payload?.success === false && payload.error) return payload as AnalysisApiError
    return toErrorPayload(`Request failed with status ${response.status}`, JSON.stringify(payload))
  } catch {
    return toErrorPayload(`Request failed with status ${response.status}`)
  }
}

export async function analyzeSpatialImage(
  imageFile: File,
  analysisMode: AnalysisMode = 'block_analysis',
): Promise<AnalysisApiResponse> {
  const endpoints = resolveCandidateEndpoints('/api/analyze')
  const attemptErrors: string[] = []
  for (const endpoint of endpoints) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        body: buildAnalysisForm(imageFile, analysisMode),
        signal: controller.signal,
      })
      if (!response.ok) {
        const parsed = await parseErrorResponse(response)
        if (response.status === 404 || response.status === 503) {
          attemptErrors.push(`${endpoint} -> HTTP ${response.status}`)
          continue
        }
        return parsed
      }
      const payload = await response.json()
      if (!isAnalysisSuccess(payload)) {
        attemptErrors.push(`${endpoint} -> Invalid payload shape`)
        continue
      }
      return payload
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown network error'
      attemptErrors.push(`${endpoint} -> ${message}`)
    } finally {
      clearTimeout(timeout)
    }
  }
  return toErrorPayload('Unable to reach analysis service.', attemptErrors.join(' | '), 'network_error')
}

export async function analyzeSpatialVideo(videoFile: File): Promise<AnalysisApiResponse> {
  const endpoints = resolveCandidateEndpoints('/api/analyze-video')
  const attemptErrors: string[] = []
  for (const endpoint of endpoints) {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), VIDEO_REQUEST_TIMEOUT_MS)
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        body: buildVideoForm(videoFile),
        signal: controller.signal,
      })
      if (!response.ok) {
        const parsed = await parseErrorResponse(response)
        if (response.status === 404 || response.status === 503) {
          attemptErrors.push(`${endpoint} -> HTTP ${response.status}`)
          continue
        }
        return parsed
      }
      const payload = await response.json()
      if (!isAnalysisSuccess(payload)) {
        attemptErrors.push(`${endpoint} -> Invalid payload shape`)
        continue
      }
      return payload
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error'
      attemptErrors.push(`${endpoint} -> ${message}`)
    } finally {
      clearTimeout(timeout)
    }
  }
  return toErrorPayload('Unable to reach video analysis service.', attemptErrors.join(' | '), 'network_error')
}

function polygonsToGeoJsonFeatures(polygons: LeafletPolygon[]) {
  return polygons
    .map((poly) => {
      if (!poly.coordinates.length) return null
      const ring = poly.coordinates.map(([lat, lng]) => [lng, lat])
      ring.push([poly.coordinates[0][1], poly.coordinates[0][0]])
      return {
        type: 'Feature' as const,
        geometry: { type: 'Polygon' as const, coordinates: [ring] },
        properties: {
          id: poly.id, category: poly.category, subcategory: poly.subcategory,
          confidence_percent: poly.confidence_percent, maintenance_priority: poly.maintenance_priority,
          condition_status: poly.condition_status, color: poly.color, layer_id: poly.layer_id,
        },
      }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
}

export async function exportGeoJSON(result: AnalysisApiSuccess): Promise<Blob> {
  const features = polygonsToGeoJsonFeatures(result.transformed.gis_mapping.leaflet_polygons)
  return new Blob([JSON.stringify({ type: 'FeatureCollection', features }, null, 2)], { type: 'application/geo+json' })
}

export async function exportCSV(result: AnalysisApiSuccess): Promise<Blob> {
  const header = ['id','category','subcategory','count','area_sq_m','coverage_percent','confidence_percent','priority','condition','center_x','center_y','shadow_length_pixels','shadow_length_meters','estimated_height_meters'].join(',')
  const rows = result.transformed.asset_table_rows.map((row) =>
    [row.id,row.category,row.subcategory,row.count,row.area_sq_m,row.coverage_percent,row.confidence_percent,row.priority,row.condition,row.center_coordinates.x,row.center_coordinates.y,row.shadow_length_pixels??0,row.shadow_length_meters??0,row.estimated_height_meters??0]
      .map((value) => `"${String(value).replace(/"/g, '""')}"`)
      .join(','),
  )
  return new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
}

// -----------------------------------------------------------------------
// New AerialEye API functions
// -----------------------------------------------------------------------

export async function semanticSearch(params: {
  q: string
  date_from?: string
  date_to?: string
  sensor?: string
  min_quality?: number
  top_k?: number
}): Promise<SearchResponse> {
  const qs = new URLSearchParams()
  qs.set('q', params.q)
  if (params.date_from) qs.set('date_from', params.date_from)
  if (params.date_to) qs.set('date_to', params.date_to)
  if (params.sensor) qs.set('sensor', params.sensor)
  if (params.min_quality != null) qs.set('min_quality', String(params.min_quality))
  if (params.top_k != null) qs.set('top_k', String(params.top_k))
  return apiFetch<SearchResponse>(`/api/search?${qs}`)
}

export async function imageSearch(params: {
  image: File
  date_from?: string
  date_to?: string
  sensor?: string
  min_quality?: number
  top_k?: number
}): Promise<SearchResponse> {
  const form = new FormData()
  form.append('image', params.image)
  if (params.date_from) form.append('date_from', params.date_from)
  if (params.date_to) form.append('date_to', params.date_to)
  if (params.sensor) form.append('sensor', params.sensor ?? '')
  if (params.min_quality != null) form.append('min_quality', String(params.min_quality))
  if (params.top_k != null) form.append('top_k', String(params.top_k))
  return apiFetch<SearchResponse>('/api/search/image', { method: 'POST', body: form })
}

export async function getObservations(assetId: string): Promise<ObservationsResponse> {
  return apiFetch<ObservationsResponse>(`/api/scenes/${assetId}/observations`)
}

export async function runChangeAnalysis(assetIdBefore: string, assetIdAfter: string): Promise<ChangeAnalysisResult> {
  const form = new FormData()
  form.append('asset_id_before', assetIdBefore)
  form.append('asset_id_after', assetIdAfter)
  return apiFetch<ChangeAnalysisResult>('/api/change-analysis', { method: 'POST', body: form }, 120_000)
}

export async function getSimilarSites(assetId: string, topK = 10): Promise<SearchResponse> {
  return apiFetch<SearchResponse>(`/api/similar-sites/${assetId}?top_k=${topK}`)
}

export async function getReviewQueue(status?: string): Promise<ReviewQueue> {
  const qs = status ? `?status=${status}` : ''
  return apiFetch<ReviewQueue>(`/api/review/queue${qs}`)
}

export async function submitReviewDecision(params: {
  candidate_id: string
  status: string
  notes?: string
  analyst_id?: string
}): Promise<{ success: boolean }> {
  const form = new FormData()
  form.append('status', params.status)
  form.append('notes', params.notes ?? '')
  form.append('analyst_id', params.analyst_id ?? 'anonymous')
  return apiFetch<{ success: boolean }>(`/api/review/${params.candidate_id}/decision`, { method: 'POST', body: form })
}

export async function getDataStatus(): Promise<DataStatus> {
  return apiFetch<DataStatus>('/api/data/status')
}

export async function ingestImage(params: {
  file: File
  sensor?: string
  acquisition_time?: string
  label?: string
}): Promise<IngestResult> {
  const form = new FormData()
  form.append('image', params.file)
  form.append('sensor', params.sensor ?? 'unknown')
  if (params.acquisition_time) form.append('acquisition_time', params.acquisition_time)
  form.append('label', params.label ?? 'REAL')
  return apiFetch<IngestResult>('/api/ingest', { method: 'POST', body: form }, 120_000)
}

export async function listAllScenes(): Promise<{ scenes: unknown[]; total: number }> {
  return apiFetch<{ scenes: unknown[]; total: number }>('/api/scenes')
}
