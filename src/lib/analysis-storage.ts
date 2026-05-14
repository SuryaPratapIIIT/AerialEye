import type { AnalysisApiSuccess } from '../types/analysis'

const STORAGE_KEY = 'aerialeye:last-analysis:v1'

export function saveLatestAnalysis(result: AnalysisApiSuccess): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(result))
  } catch {
    // Do not crash UI when localStorage is unavailable.
  }
}

export function getLatestAnalysis(): AnalysisApiSuccess | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || parsed.success !== true || !parsed.data || !parsed.transformed) return null
    return parsed as AnalysisApiSuccess
  } catch {
    return null
  }
}

export function clearLatestAnalysis(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // no-op
  }
}
