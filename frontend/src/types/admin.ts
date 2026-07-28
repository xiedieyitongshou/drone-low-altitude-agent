import type { JsonValue } from './agent'

export type AdminUser = {
  id: string
  username: string
  display_name: string | null
  role: 'user' | 'admin'
  is_active: boolean
  created_at: string
  updated_at: string
}

export type AdminUserListResponse = {
  items: AdminUser[]
  page: number
  page_size: number
  total: number
}

export type AdminConversationSummary = {
  conversation_id: string
  session_id: string | null
  user_id: string
  username: string | null
  display_name: string | null
  query: string
  intent: string | null
  target_endpoint: string | null
  parser_source: string | null
  success: boolean
  message: string | null
  created_at: string
}

export type AdminConversationListResponse = {
  items: AdminConversationSummary[]
  page: number
  page_size: number
  total: number
}

export type AdminConversationDetail = AdminConversationSummary & {
  parsed: Record<string, JsonValue> | null
  context_used: boolean
  explanation: string | null
  response: Record<string, JsonValue> | null
}

export type AdminTaskStats = {
  total_users: number
  active_users: number
  disabled_users: number
  admin_users: number
  total_tasks: number
  successful_tasks: number
  failed_tasks: number
  high_risk_tasks: number
  rule_rejected_tasks: number
  parser_failed_tasks: number
}
