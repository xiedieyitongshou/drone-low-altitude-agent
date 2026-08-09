import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  getConversationDetail,
  getCruiseHistory,
  getCruiseHistoryComposed,
  listConversations,
} from '../api/history'
import {
  AgentRuntimeSummary,
  getTraceIdFromResponse,
} from '../components/AgentRuntimeSummary'
import { JsonDetails } from '../components/JsonDetails'
import { KnowledgeAdvicePanel } from '../components/KnowledgeAdvicePanel'
import type {
  ConversationDetailResponse,
  ConversationSummary,
  CruiseHistoryResponse,
  UnifiedBusinessResponse,
} from '../types/history'

function getDecisionClass(decision?: string | null) {
  if (decision === '适飞') {
    return 'suitable'
  }

  if (decision === '禁飞') {
    return 'prohibited'
  }

  return 'caution'
}

function getRequestValue(
  request: Record<string, string | boolean | null> | undefined,
  key: string,
) {
  const value = request?.[key]
  return typeof value === 'string' ? value : '-'
}

export function HistoryPage() {
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [conversationList, setConversationList] = useState<ConversationSummary[]>([])
  const [total, setTotal] = useState(0)
  const [selectedConversation, setSelectedConversation] =
    useState<ConversationDetailResponse | null>(null)
  const [requestId, setRequestId] = useState('')
  const [history, setHistory] = useState<CruiseHistoryResponse | null>(null)
  const [composed, setComposed] = useState<UnifiedBusinessResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [debugErrorMessage, setDebugErrorMessage] = useState('')
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [isLoadingDebug, setIsLoadingDebug] = useState(false)

  useEffect(() => {
    void loadConversationList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  async function loadConversationList(nextPage = page, nextKeyword = keyword) {
    setIsLoadingList(true)
    setErrorMessage('')

    try {
      const response = await listConversations({
        page: nextPage,
        page_size: 10,
        keyword: nextKeyword.trim() || undefined,
      })
      setConversationList(response.items)
      setTotal(response.total)
      setPage(response.page)
      if (response.items.length === 0) {
        setSelectedConversation(null)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '查询对话历史失败')
    } finally {
      setIsLoadingList(false)
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await loadConversationList(1, keyword)
  }

  async function handleSelectConversation(conversationId: string) {
    setIsLoadingDetail(true)
    setErrorMessage('')

    try {
      const response = await getConversationDetail(conversationId)
      setSelectedConversation(response)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '查询对话详情失败')
    } finally {
      setIsLoadingDetail(false)
    }
  }

  async function handleDebugSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedRequestId = requestId.trim()

    if (!trimmedRequestId) {
      setDebugErrorMessage('请输入 request_id。')
      return
    }

    setIsLoadingDebug(true)
    setDebugErrorMessage('')
    setHistory(null)
    setComposed(null)

    try {
      const [historyResponse, composedResponse] = await Promise.all([
        getCruiseHistory(trimmedRequestId),
        getCruiseHistoryComposed(trimmedRequestId),
      ])
      setHistory(historyResponse)
      setComposed(composedResponse)
    } catch (error) {
      setDebugErrorMessage(error instanceof Error ? error.message : '查询失败')
    } finally {
      setIsLoadingDebug(false)
    }
  }

  const totalPages = Math.max(Math.ceil(total / 10), 1)
  const selectedTraceId = getTraceIdFromResponse(selectedConversation?.response)

  return (
    <section className="page-card history-page">
      <div className="page-header">
        <div>
          <h2>我的历史记录</h2>
          <p>
            默认调用 <code>/agent/conversations</code>
            查询当前登录用户自己的对话历史。trace 和 runtime 信息来自后端保存的历史响应，前端只展示入口和摘要。
          </p>
        </div>
      </div>

      <form className="agent-form history-search-form" onSubmit={handleSearch}>
        <label>
          <span>关键词检索</span>
          <input
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="搜索 query / message / explanation，例如：深圳"
          />
        </label>
        <div className="form-actions">
          <button type="submit" disabled={isLoadingList}>
            {isLoadingList ? '检索中...' : '检索我的历史'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setKeyword('')
              void loadConversationList(1, '')
            }}
          >
            清空条件
          </button>
        </div>
      </form>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

      <div className="conversation-layout">
        <section className="result-section conversation-list-panel">
          <div className="section-heading-row">
            <h3>对话列表</h3>
            <span>
              共 {total} 条 / 第 {page} 页
            </span>
          </div>

          {isLoadingList ? <div className="loading-panel">正在加载历史列表...</div> : null}

          {!isLoadingList && conversationList.length === 0 ? (
            <div className="empty-panel">暂无对话历史，或当前关键词没有命中记录。</div>
          ) : null}

          <div className="conversation-list">
            {conversationList.map((item) => (
              <button
                key={item.conversation_id}
                type="button"
                className={
                  selectedConversation?.conversation_id === item.conversation_id
                    ? 'conversation-item active'
                    : 'conversation-item'
                }
                onClick={() => void handleSelectConversation(item.conversation_id)}
              >
                <strong>{item.query}</strong>
                <span>{item.message ?? '暂无摘要'}</span>
                <small>
                  {item.intent ?? '-'} / {item.parser_source ?? '-'} / {item.created_at}
                </small>
              </button>
            ))}
          </div>

          <div className="pagination-row">
            <button
              type="button"
              className="secondary-button"
              disabled={page <= 1 || isLoadingList}
              onClick={() => setPage((current) => Math.max(current - 1, 1))}
            >
              上一页
            </button>
            <span>
              {page} / {totalPages}
            </span>
            <button
              type="button"
              className="secondary-button"
              disabled={page >= totalPages || isLoadingList}
              onClick={() => setPage((current) => current + 1)}
            >
              下一页
            </button>
          </div>
        </section>

        <section className="result-section conversation-detail-panel">
          <h3>对话详情</h3>
          {isLoadingDetail ? <div className="loading-panel">正在加载对话详情...</div> : null}
          {!selectedConversation && !isLoadingDetail ? (
            <div className="empty-panel">点击左侧某条历史记录查看完整详情。</div>
          ) : null}

          {selectedConversation ? (
            <>
              <div className="message-query">
                <span>用户输入</span>
                <p>{selectedConversation.query}</p>
              </div>
              <div className="explanation-panel">
                <span>系统摘要</span>
                <p>{selectedConversation.message ?? '暂无摘要。'}</p>
              </div>
              <div className="response-badges">
                <span>success: {String(selectedConversation.success)}</span>
                <span>context_used: {String(selectedConversation.context_used)}</span>
                <span>intent: {selectedConversation.intent ?? '-'}</span>
                <span>parser_source: {selectedConversation.parser_source ?? '-'}</span>
                <span>trace_id: {selectedTraceId || '-'}</span>
              </div>
              {selectedTraceId ? (
                <div className="trace-placeholder">
                  Trace 明细查询入口已保留：{selectedTraceId}。当前页面只展示摘要，时间线查询由 Day116 TraceTimeline 接入。
                </div>
              ) : null}
              <AgentRuntimeSummary response={selectedConversation.response} compact />
              <JsonDetails title="parsed" data={selectedConversation.parsed ?? {}} />
              <JsonDetails title="response" data={selectedConversation.response ?? {}} />
            </>
          ) : null}
        </section>
      </div>

      <section className="result-section debug-history-panel">
        <h3>request_id 调试复盘</h3>
        <p>
          该入口保留给调试和面试展示，用于调用 <code>/cruise/history/{'{request_id}'}</code>
          和 <code>/cruise/history/{'{request_id}'}/composed</code>。
        </p>

        <form className="agent-form history-form" onSubmit={handleDebugSubmit}>
          <label>
            <span>request_id</span>
            <input
              value={requestId}
              onChange={(event) => setRequestId(event.target.value)}
              placeholder="从单地点评估结果或对话详情 JSON 中复制 request_id"
            />
          </label>
          <div className="form-actions">
            <button type="submit" disabled={isLoadingDebug}>
              {isLoadingDebug ? '查询中...' : '调试查询'}
            </button>
          </div>
        </form>

        {debugErrorMessage ? <div className="error-panel">{debugErrorMessage}</div> : null}

        {history ? (
          <div className="history-result">
            <div className={`decision-card ${getDecisionClass(history.advice.overall_decision)}`}>
              <div>
                <span>历史任务结论</span>
                <strong>{history.advice.overall_decision}</strong>
                <p>{history.advice.allow_cruise ? '该历史任务允许执行' : '该历史任务不建议执行'}</p>
              </div>
              <div>
                <span>request_id</span>
                <code>{history.request_id}</code>
              </div>
            </div>

            <div className="summary-grid">
              <div>
                <span>创建时间</span>
                <strong>{history.created_at}</strong>
              </div>
              <div>
                <span>地点</span>
                <strong>{getRequestValue(history.request, 'location')}</strong>
              </div>
              <div>
                <span>任务类型</span>
                <strong>{getRequestValue(history.request, 'task_type')}</strong>
              </div>
            </div>

            {composed ? (
              <section className="result-section">
                <h3>统一解释</h3>
                <div className="explanation-panel">
                  <span>summary</span>
                  <p>{composed.summary}</p>
                </div>
                <div className="explanation-panel">
                  <span>explanation</span>
                  <p>{composed.explanation ?? '暂无统一解释。'}</p>
                </div>
                <KnowledgeAdvicePanel details={composed.details} />
              </section>
            ) : null}

            <JsonDetails
              title="历史评估响应 JSON"
              data={history as unknown as Record<string, never>}
            />
            <JsonDetails
              title="统一业务响应 JSON"
              data={composed as unknown as Record<string, never>}
            />
          </div>
        ) : null}
      </section>
    </section>
  )
}
