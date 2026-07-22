import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { queryAgent } from '../api/agent'
import { JsonDetails } from '../components/JsonDetails'
import { KnowledgeAdvicePanel } from '../components/KnowledgeAdvicePanel'
import type { AgentMessage } from '../types/agent'

const defaultQuery = '帮我评估深圳明天下午2点到5点是否适合日常巡航'

function createDefaultSessionId() {
  return `web-${Date.now()}`
}

export function AgentPage() {
  const [query, setQuery] = useState(defaultQuery)
  const [sessionId, setSessionId] = useState(createDefaultSessionId)
  const [userId, setUserId] = useState('default_user')
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
        user_id: userId.trim() || 'default_user',
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
          <p className="eyebrow">Day 37</p>
          <h2>Agent 自然语言入口</h2>
          <p>
            该页面调用 <code>/agent/query</code>
            ，用于演示自然语言解析、任务编排和多轮上下文继承。
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
          <label>
            <span>user_id</span>
            <input
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              placeholder="默认 default_user"
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
          <span>intent</span>
          <strong>{latestResponse?.intent ?? '-'}</strong>
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
                  <div className="explanation-panel">
                    <span>explanation</span>
                    <p>
                      {typeof message.response.composed?.explanation === 'string'
                        ? message.response.composed.explanation
                        : message.response.message}
                    </p>
                  </div>

                  <div className="response-badges">
                    <span>success: {String(message.response.success)}</span>
                    <span>context_used: {String(message.response.context_used)}</span>
                    <span>conversation_id: {message.response.conversation_id ?? '-'}</span>
                  </div>

                  <KnowledgeAdvicePanel
                    details={
                      message.response.composed?.details &&
                      typeof message.response.composed.details === 'object' &&
                      !Array.isArray(message.response.composed.details)
                        ? message.response.composed.details
                        : null
                    }
                  />

                  <JsonDetails title="parsed" data={message.response.parsed} />
                  <JsonDetails title="composed" data={message.response.composed} />
                  <JsonDetails title="result" data={message.response.result} />
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
