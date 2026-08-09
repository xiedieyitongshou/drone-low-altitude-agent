export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

export type AgentQueryRequest = {
  query: string
  session_id?: string | null
  user_id?: string
}

export type ParserSource = 'rule' | 'llm' | 'llm_fallback_rule' | string

export type AgentRuntimeDebug = {
  mode?: string
  trace_id?: string
  run_id?: string
  status?: string
  fallback_used?: boolean
  plan_actions?: string[]
  tool_results?: string[]
  error?: string
  errors?: JsonValue[]
  context_merge?: {
    field_sources?: Record<string, JsonValue>
    modified_fields?: string[]
    invalidated_tools?: string[]
  }
}

export type AgentQueryResponse = {
  success: boolean
  session_id?: string | null
  user_id: string
  conversation_id?: string | null
  intent: string
  target_endpoint: string
  parser_source: ParserSource
  parsed: Record<string, JsonValue>
  context_used: boolean
  message: string
  warnings: string[]
  composed?: Record<string, JsonValue> | null
  result?: Record<string, JsonValue> | null
  fallback?: Record<string, JsonValue> | null
  agent_runtime?: AgentRuntimeDebug | null
}

export type AgentMessage = {
  id: string
  query: string
  response?: AgentQueryResponse
  error?: string
}
