import { AxiosError } from 'axios'
import { useState } from 'react'
import { getAgentTrace } from '../api/trace'
import { JsonDetails } from './JsonDetails'
import type { AgentTraceDetailResponse, AgentTraceEvent } from '../types/trace'

type TraceTimelineProps = {
  traceId?: string | null
}

export function TraceTimeline({ traceId }: TraceTimelineProps) {
  const [trace, setTrace] = useState<AgentTraceDetailResponse | null>(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [hasRequested, setHasRequested] = useState(false)

  if (!traceId) {
    return <div className="trace-empty-panel">当前响应没有 trace 信息。</div>
  }

  async function loadTrace() {
    if (!traceId || isLoading) {
      return
    }

    setIsLoading(true)
    setError('')
    setHasRequested(true)

    try {
      const data = await getAgentTrace(traceId)
      setTrace(data)
    } catch (unknownError) {
      setTrace(null)
      setError(formatTraceError(unknownError))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="trace-timeline-panel">
      <button type="button" className="trace-link-button" onClick={loadTrace}>
        trace_id: {traceId}
      </button>
      <span className="trace-hint">点击查看执行链路</span>

      {isLoading ? <div className="loading-panel">正在查询 Trace...</div> : null}
      {error ? <div className="trace-error-panel">{error}</div> : null}

      {trace ? (
        <div className="trace-timeline">
          <div className="trace-summary-grid">
            <div>
              <span>trace_id</span>
              <strong>{trace.trace_id}</strong>
            </div>
            <div>
              <span>run_id</span>
              <strong>{trace.run_id ?? '-'}</strong>
            </div>
            <div>
              <span>session_id</span>
              <strong>{trace.session_id ?? '-'}</strong>
            </div>
            <div>
              <span>event_count</span>
              <strong>{trace.event_count}</strong>
            </div>
          </div>

          {trace.events.length ? (
            <ol className="trace-event-list">
              {trace.events.map((event) => (
                <TraceEventItem key={event.id} event={event} />
              ))}
            </ol>
          ) : (
            <div className="trace-empty-panel">暂无 trace 事件。</div>
          )}
        </div>
      ) : null}

      {!trace && hasRequested && !isLoading && !error ? (
        <div className="trace-empty-panel">暂无 trace 事件。</div>
      ) : null}
    </section>
  )
}

function TraceEventItem({ event }: { event: AgentTraceEvent }) {
  return (
    <li className={`trace-event-item ${event.event_type}`}>
      <div className="trace-event-header">
        <span className="trace-step">#{event.step_index ?? '-'}</span>
        <strong>{formatEventType(event.event_type)}</strong>
        {event.tool_name ? <span>{event.tool_name}</span> : null}
        {event.latency_ms !== null && event.latency_ms !== undefined ? (
          <span>{event.latency_ms} ms</span>
        ) : null}
      </div>

      <div className="trace-event-meta">
        {event.status_before || event.status_after ? (
          <span>
            {event.status_before ?? '-'} {'->'} {event.status_after ?? '-'}
          </span>
        ) : null}
        {event.error_code ? <span>error: {event.error_code}</span> : null}
        <span>{formatCreatedAt(event.created_at)}</span>
      </div>

      {event.message ? <p className="trace-event-message">{event.message}</p> : null}

      <div className="trace-detail-grid">
        <JsonDetails title="input_summary" data={event.input_summary ?? null} />
        <JsonDetails title="output_summary" data={event.output_summary ?? null} />
        <JsonDetails title="metadata" data={event.metadata ?? {}} />
      </div>
    </li>
  )
}

function formatEventType(eventType: string) {
  const labels: Record<string, string> = {
    plan: '计划',
    tool_call: '工具调用',
    tool_result: '工具结果',
    error: '错误',
    fallback: 'Fallback',
    final_response: '最终响应',
  }
  return labels[eventType] ?? eventType
}

function formatCreatedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatTraceError(error: unknown) {
  if (error instanceof AxiosError) {
    if (error.response?.status === 401) {
      return '登录状态已失效，请重新登录后再查看 Trace。'
    }
    if (error.response?.status === 404) {
      return 'Trace 不存在，或当前账号无权访问该执行链路。'
    }
    return `Trace 查询失败：HTTP ${error.response?.status ?? 'unknown'}`
  }

  return error instanceof Error ? error.message : 'Trace 查询失败，请稍后重试。'
}
