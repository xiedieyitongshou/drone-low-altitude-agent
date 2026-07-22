import type { CruiseAssessmentAdvice, TaskType } from './evaluation'
import type { RecommendationWindow } from './recommendation'

export type MultiLocationComparisonRequest = {
  locations: string[]
  date: string
  start_time: string
  end_time: string
  task_type: TaskType
  purpose?: string | null
  top_k: number
  comparison_mode: string
}

export type ComparedLocationResult = {
  rank: number
  location: string
  available: boolean
  location_id?: string | null
  overall_decision?: string | null
  allow_cruise?: boolean | null
  risk_score?: number | null
  score?: number | null
  flyable_hour_count: number
  max_continuous_flyable_hours: number
  earliest_flyable_time?: string | null
  window_quality_score?: number | null
  best_window?: RecommendationWindow | null
  score_breakdown: Record<string, number>
  summary_risk_factors: string[]
  error_message?: string | null
  advice?: CruiseAssessmentAdvice | null
}

export type MultiLocationComparisonResponse = {
  request: Record<string, unknown>
  comparisons: ComparedLocationResult[]
  top_k_locations: ComparedLocationResult[]
  recommended_location?: ComparedLocationResult | null
}
