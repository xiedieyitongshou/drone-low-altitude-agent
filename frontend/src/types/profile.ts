export type UserProfile = {
  user_id: string
  default_location?: string | null
  default_task_type?: string | null
  default_start_time?: string | null
  default_end_time?: string | null
  output_style?: string | null
  common_locations: string[]
  common_task_types: string[]
  created_at: string
  updated_at: string
}

export type UserProfileUpdateRequest = {
  default_location?: string | null
  default_task_type?: string | null
  default_start_time?: string | null
  default_end_time?: string | null
  output_style?: string | null
  common_locations?: string[] | null
  common_task_types?: string[] | null
}
