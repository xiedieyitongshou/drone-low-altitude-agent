import { useEffect, useState } from 'react'
import {
  getAdminConversationDetail,
  listAdminConversations,
} from '../api/admin'
import { JsonDetails } from '../components/JsonDetails'
import type {
  AdminConversationDetail,
  AdminConversationSummary,
} from '../types/admin'

export function AdminConversationsPage() {
  const [items, setItems] = useState<AdminConversationSummary[]>([])
  const [selected, setSelected] = useState<AdminConversationDetail | null>(null)
  const [filters, setFilters] = useState({
    keyword: '',
    user_id: '',
    intent: '',
    parser_source: '',
    success: '' as boolean | '',
    created_from: '',
    created_to: '',
  })
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)

  useEffect(() => {
    void loadConversations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  async function loadConversations(nextPage = page) {
    setIsLoadingList(true)
    setErrorMessage('')
    try {
      const response = await listAdminConversations({
        page: nextPage,
        page_size: 10,
        ...filters,
      })
      setItems(response.items)
      setTotal(response.total)
      setPage(response.page)
      if (response.items.length === 0) {
        setSelected(null)
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载审计列表失败')
    } finally {
      setIsLoadingList(false)
    }
  }

  async function handleSelect(conversationId: string) {
    setIsLoadingDetail(true)
    setErrorMessage('')
    try {
      setSelected(await getAdminConversationDetail(conversationId))
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载审计详情失败')
    } finally {
      setIsLoadingDetail(false)
    }
  }

  const totalPages = Math.max(Math.ceil(total / 10), 1)

  return (
    <section className="page-card admin-page">
      <div className="page-header">
        <div>
          <h2>管理员任务审计</h2>
          <p>跨用户只读查看任务输入、解析结果、业务响应和 explanation，用于排查异常和复盘风险任务。</p>
        </div>
      </div>

      <form
        className="agent-form admin-filter-form"
        onSubmit={(event) => {
          event.preventDefault()
          void loadConversations(1)
        }}
      >
        <label>
          <span>关键词</span>
          <input
            value={filters.keyword}
            onChange={(event) => setFilters((current) => ({ ...current, keyword: event.target.value }))}
          />
        </label>
        <label>
          <span>user_id</span>
          <input
            value={filters.user_id}
            onChange={(event) => setFilters((current) => ({ ...current, user_id: event.target.value }))}
          />
        </label>
        <label>
          <span>intent</span>
          <input
            value={filters.intent}
            onChange={(event) => setFilters((current) => ({ ...current, intent: event.target.value }))}
          />
        </label>
        <label>
          <span>parser_source</span>
          <input
            value={filters.parser_source}
            onChange={(event) => setFilters((current) => ({ ...current, parser_source: event.target.value }))}
          />
        </label>
        <label>
          <span>成功状态</span>
          <select
            value={filters.success === '' ? '' : String(filters.success)}
            onChange={(event) => {
              const value = event.target.value
              setFilters((current) => ({
                ...current,
                success: value === '' ? '' : value === 'true',
              }))
            }}
          >
            <option value="">全部</option>
            <option value="true">成功</option>
            <option value="false">失败</option>
          </select>
        </label>
        <label>
          <span>开始时间</span>
          <input
            type="datetime-local"
            value={filters.created_from}
            onChange={(event) => setFilters((current) => ({ ...current, created_from: event.target.value }))}
          />
        </label>
        <label>
          <span>结束时间</span>
          <input
            type="datetime-local"
            value={filters.created_to}
            onChange={(event) => setFilters((current) => ({ ...current, created_to: event.target.value }))}
          />
        </label>
        <div className="form-actions">
          <button type="submit" disabled={isLoadingList}>
            {isLoadingList ? '查询中...' : '查询审计记录'}
          </button>
        </div>
      </form>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

      <div className="conversation-layout">
        <section className="result-section conversation-list-panel">
          <div className="section-heading-row">
            <h3>全局任务列表</h3>
            <span>共 {total} 条</span>
          </div>
          {items.length === 0 && !isLoadingList ? <div className="empty-panel">暂无审计记录。</div> : null}
          <div className="conversation-list">
            {items.map((item) => (
              <button
                key={item.conversation_id}
                type="button"
                className={selected?.conversation_id === item.conversation_id ? 'conversation-item active' : 'conversation-item'}
                onClick={() => void handleSelect(item.conversation_id)}
              >
                <strong>{item.query}</strong>
                <span>
                  {item.username ?? item.user_id} / {item.intent ?? '-'} / {item.success ? '成功' : '失败'}
                </span>
                <small>{item.created_at}</small>
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
          <h3>审计详情</h3>
          {isLoadingDetail ? <div className="loading-panel">正在加载详情...</div> : null}
          {!selected && !isLoadingDetail ? <div className="empty-panel">点击左侧记录查看详情。</div> : null}
          {selected ? (
            <>
              <div className="summary-grid">
                <div>
                  <span>用户</span>
                  <strong>{selected.username ?? selected.user_id}</strong>
                </div>
                <div>
                  <span>状态</span>
                  <strong>{selected.success ? '成功' : '失败'}</strong>
                </div>
                <div>
                  <span>解析来源</span>
                  <strong>{selected.parser_source ?? '-'}</strong>
                </div>
              </div>
              <div className="message-query">
                <span>用户输入</span>
                <p>{selected.query}</p>
              </div>
              <div className="explanation-panel">
                <span>explanation</span>
                <p>{selected.explanation ?? selected.message ?? '暂无说明'}</p>
              </div>
              <JsonDetails title="parsed" data={selected.parsed ?? {}} />
              <JsonDetails title="response" data={selected.response ?? {}} />
            </>
          ) : null}
        </section>
      </div>
    </section>
  )
}
