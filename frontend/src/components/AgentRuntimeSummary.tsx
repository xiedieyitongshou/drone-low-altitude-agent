import { JsonDetails } from './JsonDetails'
import type { AgentRuntimeDebug, JsonValue } from '../types/agent'

type AgentRuntimeSummaryProps = {
  response?: Record<string, JsonValue> | null
  compact?: boolean
}

type RuntimeFallback = {
  message?: JsonValue
  suggestion?: JsonValue
  missing_fields?: JsonValue
  errors?: JsonValue
  [key: string]: JsonValue | undefined
}

export function AgentRuntimeSummary({ response, compact = false }: AgentRuntimeSummaryProps) {
  const runtime = readObject<AgentRuntimeDebug>(response?.agent_runtime)
  const fallback = readObject<RuntimeFallback>(response?.fallback)
  const errors = formatRuntimeErrors(runtime)
  const traceId = runtime?.trace_id ?? ''

  if (!runtime && !fallback) {
    return (
      <div className="runtime-empty-panel">
        当前记录未返回 Agent Runtime 或 fallback 调试信息。
      </div>
    )
  }

  return (
    <section className={compact ? 'runtime-summary compact' : 'runtime-summary'}>
      <div className="runtime-summary-header">
        <div>
          <h3>Agent Runtime 摘要</h3>
          <p>这里展示历史响应中已保存的运行摘要；Trace 明细查询留给 Day116 的时间线能力。</p>
        </div>
        {traceId ? <span className="trace-id-badge">trace_id: {traceId}</span> : null}
      </div>

      {runtime ? (
        <>
          <div className="runtime-grid">
            <div>
              <span>mode</span>
              <strong>{runtime.mode ?? '-'}</strong>
            </div>
            <div>
              <span>status</span>
              <strong>{runtime.status ?? '-'}</strong>
            </div>
            <div>
              <span>fallback_used</span>
              <strong>{String(Boolean(runtime.fallback_used))}</strong>
            </div>
            <div>
              <span>run_id</span>
              <strong>{runtime.run_id ?? '-'}</strong>
            </div>
          </div>

          <RuntimeChips title="工具结果" items={runtime.tool_results} />
          <RuntimeChips title="计划动作" items={runtime.plan_actions} />

          {errors.length ? (
            <div className="runtime-error-list">
              <strong>失败类型 / 错误信息</strong>
              <ul>
                {errors.map((error, index) => (
                  <li key={`${error}-${index}`}>{error}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}

      {fallback ? (
        <div className="fallback-panel">
          <strong>fallback 决策</strong>
          <p>{formatFallback(fallback)}</p>
        </div>
      ) : null}

      {runtime?.context_merge ? (
        <JsonDetails title="context_merge" data={runtime.context_merge} />
      ) : null}
    </section>
  )
}

export function getTraceIdFromResponse(response?: Record<string, JsonValue> | null) {
  const runtime = readObject<AgentRuntimeDebug>(response?.agent_runtime)
  return runtime?.trace_id ?? ''
}

function RuntimeChips({ title, items }: { title: string; items?: string[] }) {
  if (!items?.length) {
    return null
  }

  return (
    <div className="runtime-list">
      <strong>{title}</strong>
      <div className="runtime-chip-row">
        {items.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </div>
  )
}

function readObject<T>(value: unknown): T | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as T) : null
}

function formatRuntimeErrors(runtime: AgentRuntimeDebug | null) {
  if (!runtime) {
    return []
  }

  const errors = runtime.errors?.map((item) => formatJsonValue(item)).filter(Boolean) ?? []
  if (runtime.error) {
    errors.unshift(runtime.error)
  }
  return errors
}

function formatFallback(fallback: RuntimeFallback) {
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

function formatJsonValue(value: JsonValue | undefined) {
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
