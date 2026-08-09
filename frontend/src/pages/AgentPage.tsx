import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { queryAgent } from '../api/agent'
import { JsonDetails } from '../components/JsonDetails'
import { KnowledgeAdvicePanel } from '../components/KnowledgeAdvicePanel'
import type {
  AgentMessage,
  AgentQueryResponse,
  AgentRuntimeDebug,
  JsonValue,
  ParserSource,
} from '../types/agent'

const defaultQuery = '帮我评估深圳明天下午2点到5点是否适合日常巡航'

const parserSourceLabels: Record<string, { label: string; description: string; tone: string }> = {
  rule: {
    label: '规则解析',
    description: '本次请求由规则解析器完成结构化解析。',
    tone: 'neutral',
  },
  llm: {
    label: 'DeepSeek 解析',
    description: '本次请求由 DeepSeek 完成自然语言结构化解析。',
    tone: 'success',
  },
  llm_fallback_rule: {
    label: 'DeepSeek fallback',
    description: 'DeepSeek 解析失败或不可用，已回退到规则解析。',
    tone: 'warning',
  },
}

function createDefaultSessionId() {
  return `web-${Date.now()}`
}

function getObjectDetails(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function getRecordField(value: unknown, field: string) {
  if (!isRecord(value)) {
    return null
  }
  return isRecord(value[field]) ? value[field] : null
}

function formatUnknownValue(value: unknown): string {
  if (value === undefined || value === null || value === '') {
    return '-'
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatUnknownValue(item)).join('、')
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function toTextList(value: unknown) {
  if (!Array.isArray(value)) {
    return []
  }
  return value.map((item) => formatUnknownValue(item)).filter((item) => item && item !== '-')
}

function formatHourTime(value: unknown) {
  const text = formatUnknownValue(value)
  if (text === '-') {
    return text
  }

  const date = new Date(text)
  if (Number.isNaN(date.getTime())) {
    return text
  }

  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatWeatherSummary(weather: unknown) {
  if (!isRecord(weather)) {
    return '暂无天气明细'
  }

  const parts = [
    weather.text ? `天气 ${formatUnknownValue(weather.text)}` : '',
    weather.temp ? `温度 ${formatUnknownValue(weather.temp)}℃` : '',
    weather.wind_speed ? `风速 ${formatUnknownValue(weather.wind_speed)} km/h` : '',
    weather.wind_scale ? `风力 ${formatUnknownValue(weather.wind_scale)}级` : '',
    weather.humidity ? `湿度 ${formatUnknownValue(weather.humidity)}%` : '',
    weather.precip ? `降水 ${formatUnknownValue(weather.precip)} mm` : '',
  ].filter(Boolean)

  return parts.length ? parts.join('，') : '暂无天气明细'
}

function getToolResultEntries(response: AgentQueryResponse) {
  const toolResults = getRecordField(response.result, 'tool_results')
  if (!toolResults) {
    return []
  }

  return Object.entries(toolResults)
    .map(([toolName, result]) => ({
      toolName,
      result: isRecord(result) ? result : null,
    }))
    .filter((item): item is { toolName: string; result: Record<string, unknown> } => Boolean(item.result))
}

function getPrimaryBusinessPayload(response: AgentQueryResponse) {
  const entries = getToolResultEntries(response)
  const runtimeToolName = response.agent_runtime?.tool_results?.[0]
  const selected = runtimeToolName
    ? entries.find((entry) => entry.toolName === runtimeToolName) ?? entries[0]
    : entries[0]

  if (selected) {
    const data = selected.result.data
    return {
      toolName: selected.toolName,
      payload: isRecord(data) ? data : selected.result,
    }
  }

  return {
    toolName: null,
    payload: isRecord(response.result) ? response.result : null,
  }
}

function getDecisionTone(decision: unknown) {
  const text = String(decision ?? '')
  if (text.includes('禁') || text.toLowerCase().includes('prohibited')) {
    return 'prohibited'
  }
  if (text.includes('适') || text.toLowerCase().includes('suitable')) {
    return 'suitable'
  }
  return 'caution'
}

function getReadableExplanation(response: AgentQueryResponse) {
  return typeof response.composed?.explanation === 'string'
    ? response.composed.explanation
    : response.message
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

function getFallbackMessage(response: AgentQueryResponse) {
  const fallback = response.fallback
  if (!fallback) {
    return ''
  }

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
    return `执行失败：${errors}`
  }

  if (suggestion) {
    return suggestion
  }

  return '后端返回了 fallback 信息，请展开 JSON 查看详情。'
}

function formatRuntimeErrors(runtime?: AgentRuntimeDebug | null) {
  if (!runtime) {
    return []
  }

  const errors = runtime.errors?.map((item) => formatJsonValue(item)).filter(Boolean) ?? []
  if (runtime.error) {
    errors.unshift(runtime.error)
  }
  return errors
}

function shouldOpenRuntime(response: AgentQueryResponse) {
  const runtime = response.agent_runtime
  if (!runtime) {
    return false
  }

  return !response.success || Boolean(runtime.fallback_used) || formatRuntimeErrors(runtime).length > 0
}

function hasContextMergeSignal(runtime?: AgentRuntimeDebug | null) {
  const merge = runtime?.context_merge
  return Boolean(
    merge?.modified_fields?.length ||
      merge?.invalidated_tools?.length ||
      Object.keys(merge?.field_sources ?? {}).length,
  )
}

function ParserSourceBadge({ source }: { source?: ParserSource | null }) {
  const config = parserSourceLabels[source ?? ''] ?? {
    label: source || '未知来源',
    description: '后端返回了未识别的 parser_source，前端按普通来源展示。',
    tone: 'neutral',
  }

  return (
    <span className={`parser-source-badge ${config.tone}`} title={config.description}>
      {config.label}
    </span>
  )
}

function WarningPanel({ warnings }: { warnings?: string[] }) {
  if (!warnings?.length) {
    return null
  }

  return (
    <div className="warning-card agent-warning-panel">
      <strong>解析提示</strong>
      <ul>
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  )
}

function FallbackPanel({ response }: { response: AgentQueryResponse }) {
  const fallbackMessage = getFallbackMessage(response)

  if (!fallbackMessage) {
    return null
  }

  return (
    <div className="fallback-panel">
      <strong>需要处理的 fallback 信息</strong>
      <p>{fallbackMessage}</p>
    </div>
  )
}

function AgentReadableAnswer({ response }: { response: AgentQueryResponse }) {
  const { toolName, payload } = getPrimaryBusinessPayload(response)
  const explanation = getReadableExplanation(response)

  if (!payload) {
    return (
      <div className="agent-answer-panel">
        <span>Agent 回答</span>
        <p>{response.message || explanation || '后端已返回响应，请展开 JSON 查看详情。'}</p>
      </div>
    )
  }

  if (response.intent === 'evaluate' || toolName === 'evaluate_flight_risk') {
    return <EvaluationAnswer response={response} payload={payload} explanation={explanation} />
  }

  if (response.intent === 'recommend' || toolName === 'recommend_flight_windows') {
    return <RecommendationAnswer response={response} payload={payload} explanation={explanation} />
  }

  if (response.intent === 'compare' || toolName === 'compare_flight_locations') {
    return <ComparisonAnswer response={response} payload={payload} explanation={explanation} />
  }

  if (response.intent === 'history' || toolName === 'query_user_history') {
    return <HistoryAnswer payload={payload} explanation={explanation} />
  }

  return (
    <div className="agent-answer-panel">
      <span>Agent 回答</span>
      <p>{response.message || explanation}</p>
    </div>
  )
}

function EvaluationAnswer({
  response,
  payload,
  explanation,
}: {
  response: AgentQueryResponse
  payload: Record<string, unknown>
  explanation: string
}) {
  const advice = getRecordField(payload, 'advice') ?? payload
  const weather = getRecordField(payload, 'weather')
  const location = getRecordField(weather, 'location')?.name ?? response.parsed.location
  const decision = advice.overall_decision
  const riskFactors = toTextList(advice.summary_risk_factors)
  const hourly = Array.isArray(advice.hourly_assessment)
    ? advice.hourly_assessment.filter(isRecord)
    : []
  const riskyHours = hourly.filter((item) => toTextList(item.risk_factors).length > 0)
  const hoursToShow = (riskyHours.length ? riskyHours : hourly).slice(0, 6)

  return (
    <div className={`agent-answer-panel ${getDecisionTone(decision)}`}>
      <span>Agent 回答</span>
      <h3>{formatUnknownValue(location)} 本次评估结论：{formatUnknownValue(decision)}</h3>
      <div className="agent-answer-grid">
        <div>
          <small>是否建议执行</small>
          <strong>{advice.allow_cruise === true ? '可以执行' : '不建议直接执行'}</strong>
        </div>
        <div>
          <small>评估日期</small>
          <strong>{formatUnknownValue(response.parsed.date)}</strong>
        </div>
        <div>
          <small>评估时段</small>
          <strong>{formatUnknownValue(response.parsed.start_time)} - {formatUnknownValue(response.parsed.end_time)}</strong>
        </div>
        <div>
          <small>小时数</small>
          <strong>{hourly.length || '-'}</strong>
        </div>
      </div>
      <div className="agent-reason-section">
        <strong>判断原因</strong>
        {riskFactors.length ? (
          <ul className="agent-answer-list">
            {riskFactors.slice(0, 6).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>{advice.allow_cruise === true ? '该时段未命中明显风险规则。' : explanation}</p>
        )}
      </div>

      {hoursToShow.length ? (
        <div className="agent-hourly-weather">
          <strong>对应时段天气</strong>
          <div className="agent-hourly-list">
            {hoursToShow.map((item, index) => {
              const factors = toTextList(item.risk_factors)
              return (
                <article key={`${formatUnknownValue(item.fx_time)}-${index}`}>
                  <div>
                    <span>{formatHourTime(item.fx_time)}</span>
                    <b className={`decision-pill ${getDecisionTone(item.decision)}`}>
                      {formatUnknownValue(item.decision)}
                    </b>
                  </div>
                  <p>{formatWeatherSummary(item.weather)}</p>
                  {factors.length ? (
                    <small>原因：{factors.join('；')}</small>
                  ) : (
                    <small>原因：未命中明显风险规则</small>
                  )}
                </article>
              )
            })}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function RecommendationAnswer({
  response,
  payload,
  explanation,
}: {
  response: AgentQueryResponse
  payload: Record<string, unknown>
  explanation: string
}) {
  const recommendation = getRecordField(payload, 'recommendation') ?? payload
  const windows = Array.isArray(recommendation.recommended_windows)
    ? recommendation.recommended_windows.filter(isRecord)
    : []
  const topWindow = windows[0]

  return (
    <div className="agent-answer-panel suitable">
      <span>Agent 回答</span>
      {topWindow ? (
        <>
          <h3>
            首选窗口：{formatUnknownValue(topWindow.start_time)} - {formatUnknownValue(topWindow.end_time)}
          </h3>
          <div className="agent-answer-grid">
            <div>
              <small>地点</small>
              <strong>{formatUnknownValue(response.parsed.location)}</strong>
            </div>
            <div>
              <small>结论</small>
              <strong>{formatUnknownValue(topWindow.overall_decision)}</strong>
            </div>
            <div>
              <small>风险分</small>
              <strong>{formatUnknownValue(topWindow.risk_score)}</strong>
            </div>
            <div>
              <small>可用窗口数</small>
              <strong>{windows.length}</strong>
            </div>
          </div>
          <ul className="agent-answer-list">
            {toTextList(topWindow.reasons).slice(0, 4).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : (
        <p>{response.message || explanation || '本次未找到满足条件的推荐窗口。'}</p>
      )}
    </div>
  )
}

function ComparisonAnswer({
  response,
  payload,
  explanation,
}: {
  response: AgentQueryResponse
  payload: Record<string, unknown>
  explanation: string
}) {
  const recommended = getRecordField(payload, 'recommended_location')
  const topLocations = Array.isArray(payload.top_k_locations) ? payload.top_k_locations.filter(isRecord) : []

  return (
    <div className="agent-answer-panel caution">
      <span>Agent 回答</span>
      <h3>
        推荐地点：{formatUnknownValue(recommended?.location ?? topLocations[0]?.location ?? response.message)}
      </h3>
      {topLocations.length ? (
        <ol className="agent-answer-rank">
          {topLocations.slice(0, 3).map((item) => (
            <li key={formatUnknownValue(item.location)}>
              <strong>{formatUnknownValue(item.location)}</strong>
              <span>{formatUnknownValue(item.overall_decision)} · 风险分 {formatUnknownValue(item.risk_score)}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p>{explanation}</p>
      )}
    </div>
  )
}

function HistoryAnswer({ payload, explanation }: { payload: Record<string, unknown>; explanation: string }) {
  const items = Array.isArray(payload.items) ? payload.items.filter(isRecord) : []

  return (
    <div className="agent-answer-panel">
      <span>Agent 回答</span>
      <h3>已查询到 {items.length || formatUnknownValue(payload.total)} 条历史记录</h3>
      {items.length ? (
        <ul className="agent-answer-list">
          {items.slice(0, 3).map((item, index) => (
            <li key={formatUnknownValue(item.conversation_id ?? item.id ?? index)}>
              {formatUnknownValue(item.title ?? item.query ?? item.intent)}
            </li>
          ))}
        </ul>
      ) : (
        <p>{explanation}</p>
      )}
    </div>
  )
}

function AgentRuntimePanel({ response }: { response: AgentQueryResponse }) {
  const runtime = response.agent_runtime

  if (!runtime) {
    return (
      <div className="runtime-empty-panel">
        当前响应未返回 Agent Runtime 调试信息，页面已按旧响应格式兼容展示。
      </div>
    )
  }

  const errors = formatRuntimeErrors(runtime)

  return (
    <details className="runtime-panel" open={shouldOpenRuntime(response)}>
      <summary>
        <span>Agent Runtime</span>
        <strong>{runtime.status ?? 'unknown'}</strong>
      </summary>

      <div className="runtime-grid">
        <div>
          <span>mode</span>
          <strong>{runtime.mode ?? '-'}</strong>
        </div>
        <div>
          <span>trace_id</span>
          <strong>{runtime.trace_id ?? '-'}</strong>
        </div>
        <div>
          <span>run_id</span>
          <strong>{runtime.run_id ?? '-'}</strong>
        </div>
        <div>
          <span>fallback_used</span>
          <strong>{String(Boolean(runtime.fallback_used))}</strong>
        </div>
      </div>

      <RuntimeList title="计划动作 plan_actions" items={runtime.plan_actions} emptyText="暂无计划动作" />
      <RuntimeList title="工具结果 tool_results" items={runtime.tool_results} emptyText="暂无工具结果" />

      {errors.length > 0 ? (
        <div className="runtime-error-list">
          <strong>运行错误</strong>
          <ul>
            {errors.map((error, index) => (
              <li key={`${error}-${index}`}>{error}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <ContextMergePanel runtime={runtime} />
    </details>
  )
}

function RuntimeList({
  title,
  items,
  emptyText,
}: {
  title: string
  items?: string[]
  emptyText: string
}) {
  return (
    <div className="runtime-list">
      <strong>{title}</strong>
      {items?.length ? (
        <div className="runtime-chip-row">
          {items.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : (
        <p>{emptyText}</p>
      )}
    </div>
  )
}

function ContextMergePanel({ runtime }: { runtime: AgentRuntimeDebug }) {
  const merge = runtime.context_merge

  if (!merge) {
    return null
  }

  return (
    <details className="context-merge-panel" open={hasContextMergeSignal(runtime)}>
      <summary>
        <span>Context Merge</span>
        <strong>{hasContextMergeSignal(runtime) ? '存在上下文合并信息' : '无上下文变更'}</strong>
      </summary>

      <RuntimeList
        title="覆盖字段 modified_fields"
        items={merge.modified_fields}
        emptyText="本轮未覆盖历史字段"
      />
      <RuntimeList
        title="失效工具 invalidated_tools"
        items={merge.invalidated_tools}
        emptyText="本轮未标记工具结果失效"
      />

      <JsonDetails title="字段来源 field_sources" data={merge.field_sources ?? {}} />
    </details>
  )
}

export function AgentPage() {
  const [query, setQuery] = useState(defaultQuery)
  const [sessionId, setSessionId] = useState(createDefaultSessionId)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)

  const latestResponse = useMemo(
    () => messages.find((message) => message.response)?.response,
    [messages],
  )

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const trimmedQuery = query.trim()
    if (!trimmedQuery) {
      return
    }

    const messageId = crypto.randomUUID()
    setIsSubmitting(true)
    setMessages((current) => [
      {
        id: messageId,
        query: trimmedQuery,
      },
      ...current,
    ])

    try {
      const response = await queryAgent({
        query: trimmedQuery,
        session_id: sessionId.trim() || null,
      })

      setMessages((current) =>
        current.map((message) =>
          message.id === messageId ? { ...message, response } : message,
        ),
      )
    } catch (error) {
      setMessages((current) =>
        current.map((message) =>
          message.id === messageId
            ? {
                ...message,
                error: error instanceof Error ? error.message : '请求失败',
              }
            : message,
        ),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  function resetSession() {
    setSessionId(createDefaultSessionId())
    setMessages([])
  }

  return (
    <section className="page-card agent-page">
      <div className="page-header">
        <div>
          <h2>Agent 自然语言入口</h2>
          <p>
            该页面调用 <code>/agent/query</code>
            ，用于演示自然语言解析、任务编排和多轮上下文继承。Runtime 面板默认折叠，失败、fallback 或存在上下文覆盖时自动展开。
          </p>
        </div>
        <button type="button" className="secondary-button" onClick={resetSession}>
          新建会话
        </button>
      </div>

      <form className="agent-form" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            <span>session_id</span>
            <input
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
              placeholder="用于多轮上下文继承"
            />
          </label>
        </div>

        <label className="query-box">
          <span>自然语言任务</span>
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={4}
            placeholder="例如：帮我评估深圳明天下午2点到5点是否适合日常巡航"
          />
        </label>

        <div className="form-actions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? '正在调用...' : '发送请求'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setQuery('那明天下午呢')}
          >
            填入上下文测试句
          </button>
        </div>
      </form>

      <div className="agent-meta-grid">
        <div>
          <span>context_used</span>
          <strong>{latestResponse ? String(latestResponse.context_used) : '-'}</strong>
        </div>
        <div>
          <span>conversation_id</span>
          <strong>{latestResponse?.conversation_id ?? '-'}</strong>
        </div>
        <div>
          <span>parser_source</span>
          <strong>{latestResponse ? <ParserSourceBadge source={latestResponse.parser_source} /> : '-'}</strong>
        </div>
      </div>

      <div className="message-list">
        {messages.length === 0 ? (
          <div className="empty-panel">
            先提交一条完整请求，再提交“那明天下午呢”这类省略表达，可验证上下文继承。
          </div>
        ) : (
          messages.map((message) => (
            <article className="message-card" key={message.id}>
              <div className="message-query">
                <span>用户输入</span>
                <p>{message.query}</p>
              </div>

              {message.error ? (
                <div className="error-panel">{message.error}</div>
              ) : message.response ? (
                <>
                  <AgentReadableAnswer response={message.response} />

                  <div className="explanation-panel compact">
                    <span>运行说明</span>
                    <p>{getReadableExplanation(message.response)}</p>
                  </div>

                  <div className="response-badges">
                    <span>success: {String(message.response.success)}</span>
                    <span>context_used: {String(message.response.context_used)}</span>
                    <span>intent: {message.response.intent ?? '-'}</span>
                    <span>target: {message.response.target_endpoint ?? '-'}</span>
                    <ParserSourceBadge source={message.response.parser_source} />
                    <span>conversation_id: {message.response.conversation_id ?? '-'}</span>
                    {message.response.agent_runtime?.trace_id ? (
                      <span>trace_id: {message.response.agent_runtime.trace_id}</span>
                    ) : null}
                  </div>

                  <WarningPanel warnings={message.response.warnings} />
                  <FallbackPanel response={message.response} />
                  <AgentRuntimePanel response={message.response} />

                  <KnowledgeAdvicePanel details={getObjectDetails(message.response.composed?.details)} />

                  <JsonDetails title="parsed" data={message.response.parsed} />
                  <JsonDetails title="composed" data={message.response.composed} />
                  <JsonDetails title="result" data={message.response.result} />
                  <JsonDetails title="fallback" data={message.response.fallback} />
                </>
              ) : (
                <div className="loading-panel">等待后端响应...</div>
              )}
            </article>
          ))
        )}
      </div>
    </section>
  )
}
