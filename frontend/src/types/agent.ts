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

export type AgentQueryResponse = {
  success: boolean
  session_id?: string | null
  user_id: string
  conversation_id?: string | null
  intent: string
  target_endpoint: string
  parser_source: string
  parsed: Record<string, JsonValue>
  context_used: boolean
  message: string
  warnings: string[]
  composed?: Record<string, JsonValue> | null
  result?: Record<string, JsonValue> | null
  fallback?: Record<string, JsonValue> | null
}

export type AgentMessage = {
  id: string
  query: string
  response?: AgentQueryResponse
  error?: string
}
