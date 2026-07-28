import type { CruiseAssessmentResponse } from './evaluation'
import type { ComparedLocationResult } from './comparison'
import type { JsonValue } from './agent'
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

export type ConversationSummary = {
  conversation_id: string
  session_id?: string | null
  query: string
  intent?: string | null
  target_endpoint?: string | null
  parser_source?: string | null
  success: boolean
  message?: string | null
  created_at: string
}

export type ConversationListResponse = {
  items: ConversationSummary[]
  page: number
  page_size: number
  total: number
}

export type ConversationDetailResponse = ConversationSummary & {
  parsed?: Record<string, JsonValue> | null
  context_used: boolean
  explanation?: string | null
  response?: Record<string, JsonValue> | null
}

export type ConversationListParams = {
  page?: number
  page_size?: number
  keyword?: string
  session_id?: string
  intent?: string
  parser_source?: string
}
