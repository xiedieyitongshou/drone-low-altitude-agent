import type { JsonValue } from './agent'
import type { UserRole } from './auth'

export type AdminUser = {
  id: string
  username: string
  display_name: string | null
  role: UserRole
  tenant_id?: string | null
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

export type KnowledgeType = 'risk_advice' | 'sop' | 'policy_hint' | 'faq'

export type KnowledgeCategory =
  | 'risk_advice'
  | 'warning_advice'
  | 'task_advice'
  | 'execution_advice'

export type KnowledgeVisibility = 'public' | 'tenant' | 'private'

export type KnowledgeReviewStatus = 'draft' | 'approved' | 'rejected' | 'expired'

export type KnowledgeIndexJobStatus = 'pending' | 'running' | 'success' | 'failed'

export type KnowledgeDocument = {
  id: string
  title: string
  content: string
  knowledge_type: KnowledgeType
  category: KnowledgeCategory | null
  region: string | null
  province: string | null
  city: string | null
  task_types: string[]
  risk_tags: string[]
  warning_types: string[]
  warning_levels: string[]
  decision_scopes: string[]
  keywords: string[]
  visibility: KnowledgeVisibility
  tenant_id: string
  user_id: string | null
  version: string
  review_status: KnowledgeReviewStatus
  is_active: boolean
  index_dirty: boolean
  effective_at: string | null
  expires_at: string | null
  source: string | null
  source_url: string | null
  metadata: Record<string, JsonValue>
  created_at: string
  updated_at: string
}

export type KnowledgeDocumentListResponse = {
  items: KnowledgeDocument[]
  page: number
  page_size: number
  total: number
}

export type KnowledgeDocumentPayload = {
  title: string
  content: string
  knowledge_type: KnowledgeType
  category?: KnowledgeCategory | null
  region?: string | null
  province?: string | null
  city?: string | null
  task_types?: string[]
  risk_tags?: string[]
  warning_types?: string[]
  warning_levels?: string[]
  decision_scopes?: string[]
  keywords?: string[]
  visibility?: KnowledgeVisibility
  tenant_id?: string
  user_id?: string | null
  version?: string
  review_status?: KnowledgeReviewStatus
  is_active?: boolean
  index_dirty?: boolean
  effective_at?: string | null
  expires_at?: string | null
  source?: string | null
  source_url?: string | null
  metadata?: Record<string, JsonValue>
}

export type KnowledgeDocumentStatusPayload = {
  review_status?: KnowledgeReviewStatus | null
  is_active?: boolean | null
  index_dirty?: boolean
}

export type KnowledgeIndexJob = {
  id: string
  status: KnowledgeIndexJobStatus
  index_type: string
  triggered_by_user_id: string | null
  document_count: number
  chunk_count: number
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  updated_at: string
}

export type KnowledgeIndexJobListResponse = {
  items: KnowledgeIndexJob[]
  page: number
  page_size: number
  total: number
}
