import type { JsonValue } from './agent'

export type TracePayload = JsonValue | JsonValue[] | Record<string, JsonValue>

export type AgentTraceEvent = {
  id: number
  trace_id: string
  run_id: string
  user_id?: string | null
  session_id?: string | null
  event_type: string
  step_index?: number | null
  status_before?: string | null
  status_after?: string | null
  tool_name?: string | null
  latency_ms?: number | null
  input_summary?: TracePayload | null
  output_summary?: TracePayload | null
  error_code?: string | null
  message?: string | null
  metadata: Record<string, JsonValue>
  created_at: string
}

export type AgentTraceDetailResponse = {
  trace_id: string
  run_id?: string | null
  user_id?: string | null
  session_id?: string | null
  event_count: number
  events: AgentTraceEvent[]
}
