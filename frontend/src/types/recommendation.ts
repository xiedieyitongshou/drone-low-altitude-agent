import type {
  HourlyAssessment,
  TaskType,
  WarningDataBundle,
  WeatherHourData,
} from './evaluation'

export type RecommendationRequest = {
  location: string
  date: string
  task_type: TaskType
  purpose?: string | null
  scan_hours: number
  min_window_hours: number
}

export type RecommendationWindow = {
  rank: number
  start_time: string
  end_time: string
  duration_hours: number
  overall_decision: string
  risk_score: number
  reasons: string[]
  hourly_assessment: HourlyAssessment[]
}

export type RecommendationResponse = {
  request: Record<string, string | number | null>
  weather?: {
    location: Record<string, string | null>
    update_time?: string | null
    hourly_weather: WeatherHourData[]
  } | null
  warnings?: WarningDataBundle | null
  recommendation: {
    strategy: {
      min_window_hours: number
      sort_rules: string[]
    }
    recommended_windows: RecommendationWindow[]
    total_candidates: number
  }
}
