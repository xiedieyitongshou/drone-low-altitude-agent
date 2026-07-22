export type TaskType = 'cruise' | 'inspection' | 'hover' | 'survey'

export type CruiseEvaluateRequest = {
  location: string
  date: string
  start_time: string
  end_time: string
  task_type: TaskType
  purpose?: string | null
}

export type WeatherHourData = {
  fx_time: string
  temp?: string | null
  text?: string | null
  wind_scale?: string | null
  wind_speed?: string | null
  humidity?: string | null
  precip?: string | null
  pop?: string | null
  pressure?: string | null
  cloud?: string | null
}

export type WarningData = {
  warning_id?: string | null
  event_type?: string | null
  warning_level?: string | null
  title?: string | null
  sender?: string | null
  publish_time?: string | null
  start_time?: string | null
  end_time?: string | null
  status?: string | null
  text?: string | null
}

export type WarningDataBundle = {
  warnings: WarningData[]
  has_warning: boolean
  warning_count: number
}

export type HourlyAssessment = {
  fx_time: string
  decision: string
  risk_factors: string[]
  weather: Record<string, string | null>
}

export type CruiseAssessmentAdvice = {
  allow_cruise: boolean
  overall_decision: string
  summary_risk_factors: string[]
  hourly_assessment: HourlyAssessment[]
}

export type CruiseAssessmentResponse = {
  request: Record<string, string | boolean | null>
  weather?: {
    location: Record<string, string | null>
    update_time?: string | null
    hourly_weather: WeatherHourData[]
  } | null
  warnings?: WarningDataBundle | null
  advice: CruiseAssessmentAdvice
}
