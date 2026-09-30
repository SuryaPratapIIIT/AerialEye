// Existing analysis types (preserved)
export interface AnalysisApiError {
  success: false
  request_id?: string
  error: {
    code: string
    message: string
    details?: string
  }
}

export interface LeafletPolygon {
  id: string
  layer_id: string
  category: string
  subcategory: string
  coordinates: [number, number][]
  color: string
  confidence_percent: number
  maintenance_priority: string
  condition_status: string
}

export interface LeafletMarker {
  id: string
  layer_id: string
  category: string
  label: string
  lat: number
  lng: number
  color: string
  confidence_percent: number
  estimated_area_sq_m: number
}

export interface AnalysisApiSuccess {
  success: true
  request_id: string
  analysis_mode: string
  data: {
    detected_assets: unknown[]
    [key: string]: unknown
  }
  transformed: {
    gis_mapping: {
      map_center: { lat: number; lng: number }
      leaflet_polygons: LeafletPolygon[]
      leaflet_markers: LeafletMarker[]
    }
    chart_data: {
      category_comparison_data: {
        category: string
        layer_id: string
        color: string
        count: number
        area_sq_m: number
        coverage_percent: number
      }[]
    }
    asset_table_rows: {
      id: string
      category: string
      subcategory: string
      count: number
      area_sq_m: number
      coverage_percent: number
      confidence_percent: number
      priority: string
      condition: string
      center_coordinates: { x: number; y: number }
      shadow_length_pixels?: number
      shadow_length_meters?: number
      estimated_height_meters?: number
    }[]
    [key: string]: unknown
  }
  warnings: string[]
  [key: string]: unknown
}

export type AnalysisApiResponse = AnalysisApiSuccess | AnalysisApiError

// ============================================================
// New AerialEye Types
// ============================================================

export type DataLabel = 'REAL' | 'HEURISTIC' | 'DEMO' | 'UNAVAILABLE'

export interface SceneResult {
  asset_id: string
  scene_id: string
  source: string
  sensor: string
  acquisition_time: string
  quality_score: number
  cloud_cover: number
  similarity_score: number
  thumbnail_b64: string
  bbox: number[]
  crs: string
  label: DataLabel
  tags: string[]
}

export interface SearchResponse {
  query?: string
  results: SceneResult[]
  total: number
  method: string
  model?: string
  label: DataLabel
  note?: string
}

export interface SceneDetail {
  asset_id: string
  scene_id: string
  source: string
  sensor: string
  acquisition_time: string
  quality_score: number
  cloud_cover: number
  thumbnail_b64: string
  crs: string
  bbox: number[]
  resolution: number
  bands: unknown[]
  ingestion_ts: number
  processing_version: string
  file_path: string
  label: DataLabel
}

export interface TemporalObservation {
  asset_id: string
  scene_id: string
  source: string
  sensor: string
  acquisition_time: string
  quality_score: number
  cloud_cover: number
  thumbnail_b64: string
  is_reference: boolean
  label: DataLabel
}

export interface ObservationsResponse {
  reference_asset_id: string
  observations: TemporalObservation[]
  total: number
  label: DataLabel
}

export interface ChangeAnalysisResult {
  success: boolean
  candidate_id?: string
  scene_before?: SceneResult
  scene_after?: SceneResult
  change_score: number
  confidence: number
  change_type: string
  change_type_description: string
  earliest_obs: string
  quality_flags: string[]
  change_map_b64: string
  method: string
  label: DataLabel
  note?: string
  error?: string
}

export type ReviewStatus = 'NEW' | 'CONFIRMED' | 'REJECTED' | 'NEEDS_REVIEW'

export interface ReviewItem {
  candidate_id: string
  status: ReviewStatus
  change_score: number
  confidence: number
  change_type: string
  earliest_obs: string
  quality_flags: string[]
  method: string
  label: DataLabel
  processing_ts: number
  change_map_b64: string
  scene_before: SceneResult | null
  scene_after: SceneResult | null
  decision: {
    notes: string
    analyst_id: string
    timestamp: number
  } | null
}

export interface ReviewQueue {
  items: ReviewItem[]
  total: number
  status_filter: string | null
}

export interface IndexStats {
  scene_count: number
  embedding_count: number
  change_candidate_count: number
  analyst_decision_count: number
  db_size_bytes: number
}

export interface ModelStatus {
  clip_available: boolean
  text_model_available: boolean
  faiss_available: boolean
  faiss_vector_count: number
  label: DataLabel
}

export interface DataStatus {
  index_stats: IndexStats
  model_status: ModelStatus
  yolo_available: boolean
  vision_api_key_loaded: boolean
  data_dir: string
}

export interface IngestResult {
  success: boolean
  status: 'ingested' | 'skipped'
  asset_id: string
  scene_id?: string
  quality_score?: number
  embedding_available?: boolean
  label?: DataLabel
  reason?: string
}
