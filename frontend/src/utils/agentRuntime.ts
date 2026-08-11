import type { AgentQueryResponse, AgentRuntimeDebug, JsonValue } from '../types/agent'

export type RuntimeFallback = {
  message?: JsonValue
  suggestion?: JsonValue
  missing_fields?: JsonValue
  errors?: JsonValue
  [key: string]: JsonValue | undefined
}

export function readObject<T>(value: unknown): T | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as T) : null
}

export function formatJsonValue(value: JsonValue | undefined) {
  if (value === undefined || value === null) {
    return ''
  }

  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join('、')
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}

export function formatRuntimeErrors(runtime?: AgentRuntimeDebug | null) {
  if (!runtime) {
    return []
  }

  const errors = runtime.errors?.map((item) => formatJsonValue(item)).filter(Boolean) ?? []
  if (runtime.error) {
    errors.unshift(runtime.error)
  }
  return errors
}

export function formatFallback(fallback: RuntimeFallback) {
  const message = formatJsonValue(fallback.message)
  const suggestion = formatJsonValue(fallback.suggestion)
  const missingFields = formatJsonValue(fallback.missing_fields)
  const errors = formatJsonValue(fallback.errors)

  if (message) {
    return message
  }

  if (missingFields) {
    return `缺少必要字段：${missingFields}`
  }

  if (errors) {
    return `错误信息：${errors}`
  }

  if (suggestion) {
    return suggestion
  }

  return '存在 fallback 输出，请展开原始 response JSON 查看完整内容。'
}

export function shouldOpenRuntime(response: AgentQueryResponse) {
  const runtime = response.agent_runtime
  if (!runtime) {
    return false
  }

  return !response.success || Boolean(runtime.fallback_used) || formatRuntimeErrors(runtime).length > 0
}

export function hasContextMergeSignal(runtime?: AgentRuntimeDebug | null) {
  const merge = runtime?.context_merge
  return Boolean(
    merge?.modified_fields?.length ||
      merge?.invalidated_tools?.length ||
      Object.keys(merge?.field_sources ?? {}).length,
  )
}

export function getTraceIdFromResponse(response?: Record<string, JsonValue> | null) {
  const runtime = readObject<AgentRuntimeDebug>(response?.agent_runtime)
  return runtime?.trace_id ?? ''
}
