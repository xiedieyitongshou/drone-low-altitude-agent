import type { JsonValue } from './agent'
import type { CruiseAssessmentResponse, TaskType } from './evaluation'
import type { RecommendationResponse, RecommendationWindow } from './recommendation'

export type MissionTaskStatus = 'draft' | 'evaluated' | 'scheduled' | 'recheck' | 'completed' | 'cancelled'

export type MissionTaskCreateRequest = {
  title: string
  purpose?: string | null
  location?: string | null
  date?: string | null
  start_time?: string | null
  end_time?: string | null
  task_type?: TaskType | null
  candidate_locations?: string[]
  metadata?: Record<string, JsonValue>
  profile_context?: Record<string, JsonValue>
}

export type MissionTaskUpdateRequest = Partial<Omit<MissionTaskCreateRequest, 'profile_context'>>

export type MissionTaskRecommendRequest = {
  scan_hours?: number
  min_window_hours?: number
}

export type MissionTaskSelectWindowRequest = {
  rank?: number
  window?: RecommendationWindow
}

export type MissionTaskResponse = {
  id: string
  user_id: string
  title: string
  purpose?: string | null
  status: MissionTaskStatus
  location?: string | null
  date?: string | null
  start_time?: string | null
  end_time?: string | null
  task_type?: string | null
  candidate_locations: string[]
  selected_window?: Record<string, JsonValue> | null
  latest_decision?: string | null
  latest_request_id?: string | null
  latest_trace_id?: string | null
  latest_conversation_id?: string | null
  created_at: string
  updated_at: string
}

export type MissionTaskListResponse = {
  items: MissionTaskResponse[]
  page: number
  page_size: number
  total: number
}

export type MissionTaskDetailResponse = MissionTaskResponse & {
  profile_context: Record<string, JsonValue>
  metadata: Record<string, JsonValue>
  conversation_ids: string[]
  request_ids: string[]
  trace_ids: string[]
}

export type MissionTaskListParams = {
  page?: number
  page_size?: number
  status?: MissionTaskStatus | ''
  keyword?: string
}

export type MissionTaskActionResult = MissionTaskResponse | CruiseAssessmentResponse | RecommendationResponse
