import type {
  AnalysisApiError,
  AnalysisApiResponse,
  AnalysisApiSuccess,
  LeafletPolygon,
} from '../types/analysis'

const REQUEST_TIMEOUT_MS = 180_000
export type AnalysisMode = 'block_analysis' | 'naming_analysis'

function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_ANALYSIS_API_BASE as string | undefined
  return (configured && configured.trim()) || ''
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
    endpoints.push(path)
    endpoints.push(`http://127.0.0.1:8000${path}`)
    endpoints.push(`http://localhost:8000${path}`)
  }

  return [...new Set(endpoints)]
}

function toErrorPayload(message: string, details = '', code = 'analysis_request_failed'): AnalysisApiError {
  return {
    success: false,
    error: {
      code,
      message,
      details,
    },
  }
}

async function parseErrorResponse(response: Response): Promise<AnalysisApiError> {
  try {
    const payload = await response.json()
    if (payload?.detail?.success === false && payload.detail.error) {
      return payload.detail as AnalysisApiError
    }
    if (payload?.success === false && payload.error) {
      return payload as AnalysisApiError
    }
    return toErrorPayload(`Request failed with status ${response.status}`, JSON.stringify(payload))
  } catch {
    return toErrorPayload(`Request failed with status ${response.status}`)
  }
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

function buildAnalysisForm(imageFile: File, analysisMode: AnalysisMode): FormData {
  const form = new FormData()
  form.append('image', imageFile)
  form.append('analysis_mode', analysisMode)
  return form
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
        if (response.status === 404 || response.status === 502 || response.status === 503) {
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
      if (error instanceof DOMException && error.name === 'AbortError') {
        attemptErrors.push(`${endpoint} -> Timeout after ${REQUEST_TIMEOUT_MS / 1000}s`)
      } else {
        const message = error instanceof Error ? error.message : 'Unknown network error'
        attemptErrors.push(`${endpoint} -> ${message}`)
      }
    } finally {
      clearTimeout(timeout)
    }
  }

  return toErrorPayload(
    'Unable to reach analysis service.',
    `Tried endpoints: ${attemptErrors.join(' | ')}. Ensure backend is running with "npm run dev:backend".`,
    'network_error',
  )
}

function polygonsToGeoJsonFeatures(polygons: LeafletPolygon[]) {
  return polygons
    .map((poly) => {
      if (!poly.coordinates.length) return null
      const ring = poly.coordinates.map(([lat, lng]) => [lng, lat])
      ring.push([poly.coordinates[0][1], poly.coordinates[0][0]])
      return {
        type: 'Feature' as const,
        geometry: {
          type: 'Polygon' as const,
          coordinates: [ring],
        },
        properties: {
          id: poly.id,
          category: poly.category,
          subcategory: poly.subcategory,
          confidence_percent: poly.confidence_percent,
          maintenance_priority: poly.maintenance_priority,
          condition_status: poly.condition_status,
          color: poly.color,
          layer_id: poly.layer_id,
        },
      }
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)
}

export async function exportGeoJSON(result: AnalysisApiSuccess): Promise<Blob> {
  const features = polygonsToGeoJsonFeatures(result.transformed.gis_mapping.leaflet_polygons)
  const geoJson = {
    type: 'FeatureCollection',
    features,
  }
  return new Blob([JSON.stringify(geoJson, null, 2)], { type: 'application/geo+json' })
}

export async function exportCSV(result: AnalysisApiSuccess): Promise<Blob> {
  const header = [
    'id',
    'category',
    'subcategory',
    'count',
    'area_sq_m',
    'coverage_percent',
    'confidence_percent',
    'priority',
    'condition',
    'center_x',
    'center_y',
  ].join(',')

  const rows = result.transformed.asset_table_rows.map((row) =>
    [
      row.id,
      row.category,
      row.subcategory,
      row.count,
      row.area_sq_m,
      row.coverage_percent,
      row.confidence_percent,
      row.priority,
      row.condition,
      row.center_coordinates.x,
      row.center_coordinates.y,
    ]
      .map((value) => `"${String(value).replace(/"/g, '""')}"`)
      .join(','),
  )

  return new Blob([[header, ...rows].join('\n')], { type: 'text/csv' })
}
