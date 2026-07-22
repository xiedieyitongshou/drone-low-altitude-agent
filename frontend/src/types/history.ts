import type { CruiseAssessmentResponse } from './evaluation'
import type { ComparedLocationResult } from './comparison'
import type { RecommendationWindow } from './recommendation'

export type CruiseHistoryResponse = CruiseAssessmentResponse & {
  request_id: string
  created_at: string
}

export type UnifiedBusinessResponse = {
  scene: 'evaluate' | 'recommend' | 'compare' | 'history'
  summary: string
  explanation?: string | null
  explanation_source: 'template' | 'llm' | 'none'
  llm_used: boolean
  overall_decision?: string | null
  allow_execute?: boolean | null
  risk_reasons: string[]
  recommended_windows: RecommendationWindow[]
  ranked_locations: ComparedLocationResult[]
  history_summary?: {
    request_id: string
    created_at: string
    location?: string | null
    task_type?: string | null
    date?: string | null
    start_time?: string | null
    end_time?: string | null
    overall_decision?: string | null
  } | null
  details: Record<string, unknown>
}
