export type CategoryName =
  | 'Properties & Buildings'
  | 'Trees & Green Cover'
  | 'Parks & Open Spaces'
  | 'Water Bodies'
  | 'Roads & Footpaths'
  | 'Drains & Sewage'
  | 'Vehicles & Parking'
  | 'Waste Dumps'
  | 'Solar Panels'
  | string

export interface NormalizedPoint {
  x: number
  y: number
}

export interface BoundingBox {
  x_min: number
  y_min: number
  x_max: number
  y_max: number
}

export interface DetectedAsset {
  unique_id: string
  category: CategoryName
  subcategory: string
  confidence_percent: number
  estimated_count: number
  estimated_area_sq_m: number
  estimated_dimensions_m: {
    length: number
    width: number
  }
  estimated_coverage_percent: number
  condition_status: string
  maintenance_priority: string
  center_coordinates: NormalizedPoint
  bounding_box: BoundingBox
  polygon_coordinates: NormalizedPoint[]
  visual_description: string
  estimation_basis: string
}

export interface ImageAnalysis {
  scene_type: string
  image_quality: string
  estimated_total_area_sq_m: number
  overall_detection_confidence_percent: number
  dominant_land_use: string
}

export interface SummaryStatistics {
  total_assets_detected: number
  green_cover_percent: number
  built_up_percent: number
  road_network_percent: number
  water_body_percent: number
  open_space_percent: number
}

export interface CategoryStatisticsItem {
  count: number
  total_area_sq_m: number
  coverage_percent: number
}

export type CategoryStatistics = Record<string, CategoryStatisticsItem>

export interface RiskAnalysis {
  encroachment_risk: string
  drainage_risk: string
  environmental_risk: string
  flood_risk: string
}

export interface StructuredAnalysis {
  image_analysis: ImageAnalysis
  summary_statistics: SummaryStatistics
  detected_assets: DetectedAsset[]
  category_statistics: CategoryStatistics
  risk_analysis: RiskAnalysis
  ai_insights: string[]
}

export interface LeafletPolygon {
  id: string
  layer_id: string
  category: string
  subcategory: string
  color: string
  confidence_percent: number
  coordinates: [number, number][]
  bbox_coordinates: [number, number][]
  center: [number, number]
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

export interface TransformedPayload {
  analytics_cards: {
    total_assets_detected: number
    green_cover_percent: number
    built_up_percent: number
    road_network_percent: number
    water_body_percent: number
    open_space_percent: number
    overall_detection_confidence_percent: number
    estimated_total_area_sq_m: number
    urban_density_score: number
  }
  asset_statistics: {
    category_counts: Record<string, number>
    category_total_area_sq_m: Record<string, number>
    maintenance_priorities: Record<string, number>
    risk_indicators: RiskAnalysis
  }
  gis_mapping: {
    map_center: { lat: number; lng: number }
    leaflet_polygons: LeafletPolygon[]
    leaflet_markers: LeafletMarker[]
    heatmap_points: [number, number, number][]
  }
  dashboard_insights: {
    ai_insights_cards: string[]
    environmental_risks: string[]
    encroachment_warnings: string[]
    drainage_observations: string[]
    governance_insights: string[]
  }
  chart_data: {
    pie_chart_data: Array<{ name: string; value: number; color: string }>
    area_distribution_data: Array<{ name: string; area_sq_m: number; color: string }>
    coverage_graph_data: Array<{ name: string; coverage_percent: number; color: string }>
    category_comparison_data: Array<{
      category: string
      count: number
      area_sq_m: number
      coverage_percent: number
      color: string
      layer_id: string
    }>
  }
  asset_table_rows: Array<{
    id: string
    category: string
    subcategory: string
    count: number
    area_sq_m: number
    coverage_percent: number
    confidence_percent: number
    priority: string
    condition: string
    center_coordinates: NormalizedPoint
    visual_description: string
    estimation_basis: string
  }>
}

export interface AnalysisApiSuccess {
  success: true
  request_id: string
  analysis_mode?: 'block_analysis' | 'naming_analysis' | string
  naming_visualization_data_url?: string
  data: StructuredAnalysis
  transformed: TransformedPayload
  warnings: string[]
}

export interface AnalysisApiErrorPayload {
  code: string
  message: string
  details?: string
}

export interface AnalysisApiError {
  success: false
  request_id?: string
  error: AnalysisApiErrorPayload
}

export type AnalysisApiResponse = AnalysisApiSuccess | AnalysisApiError
