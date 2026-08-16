import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createMissionTask,
  evaluateMissionTask,
  getMissionTask,
  listMissionTasks,
  preflightCheckMissionTask,
  recommendMissionTaskWindows,
  selectMissionTaskWindow,
  updateMissionTaskStatus,
} from '../api/missionTasks'
import { getCruiseHistory, getCruiseHistoryComposed } from '../api/history'
import { JsonDetails } from '../components/JsonDetails'
import { KnowledgeAdvicePanel } from '../components/KnowledgeAdvicePanel'
import { TraceTimeline } from '../components/TraceTimeline'
import type { JsonValue } from '../types/agent'
import type { CruiseAssessmentResponse, TaskType } from '../types/evaluation'
import type { CruiseHistoryResponse, UnifiedBusinessResponse } from '../types/history'
import type {
  MissionTaskDetailResponse,
  MissionTaskResponse,
  MissionTaskStatus,
} from '../types/missionTask'
import type { RecommendationResponse } from '../types/recommendation'

const PAGE_SIZE = 10

const statusOptions: Array<{ value: MissionTaskStatus | ''; label: string }> = [
  { value: '', label: '全部状态' },
  { value: 'draft', label: '草稿' },
  { value: 'evaluated', label: '已评估' },
  { value: 'scheduled', label: '已排期' },
  { value: 'recheck', label: '已复核' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
]

const taskTypeOptions: Array<{ value: TaskType; label: string }> = [
  { value: 'cruise', label: '巡航' },
  { value: 'inspection', label: '巡检' },
  { value: 'hover', label: '悬停' },
  { value: 'survey', label: '测绘' },
]

type CreateTaskForm = {
  title: string
  purpose: string
  location: string
  date: string
  start_time: string
  end_time: string
  task_type: TaskType
  candidate_locations: string
}

type LastAction =
  | { kind: 'task'; result: MissionTaskResponse }
  | { kind: 'evaluation'; result: CruiseAssessmentResponse }
  | { kind: 'recommendation'; result: RecommendationResponse }
  | null

const initialForm: CreateTaskForm = {
  title: '',
  purpose: '',
  location: '',
  date: '',
  start_time: '13:00',
  end_time: '18:00',
  task_type: 'inspection',
  candidate_locations: '',
}

export function MissionTasksPage() {
  const [tasks, setTasks] = useState<MissionTaskResponse[]>([])
  const [selectedTask, setSelectedTask] = useState<MissionTaskDetailResponse | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState('')
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState<MissionTaskStatus | ''>('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [form, setForm] = useState<CreateTaskForm>(initialForm)
  const [lastAction, setLastAction] = useState<LastAction>(null)
  const [historyByRequestId, setHistoryByRequestId] = useState<Record<string, CruiseHistoryResponse>>({})
  const [composedByRequestId, setComposedByRequestId] = useState<Record<string, UnifiedBusinessResponse>>({})
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isLoadingList, setIsLoadingList] = useState(false)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [runningAction, setRunningAction] = useState('')

  useEffect(() => {
    void loadTasks(page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const latestRecommendation = useMemo(
    () => readLatestRecommendation(selectedTask?.metadata),
    [selectedTask],
  )
  const recommendedWindows = latestRecommendation?.recommendation.recommended_windows ?? []
  const totalPages = Math.max(Math.ceil(total / PAGE_SIZE), 1)

  async function loadTasks(nextPage = page, nextKeyword = keyword, nextStatus = statusFilter) {
    setIsLoadingList(true)
    setErrorMessage('')

    try {
      const response = await listMissionTasks({
        page: nextPage,
        page_size: PAGE_SIZE,
        keyword: nextKeyword.trim() || undefined,
        status: nextStatus || undefined,
      })
      setTasks(response.items)
      setTotal(response.total)
      setPage(response.page)
      if (selectedTaskId && response.items.every((item) => item.id !== selectedTaskId)) {
        setSelectedTask(null)
        setSelectedTaskId('')
      }
    } catch (error) {
      setErrorMessage(formatError(error, '加载任务列表失败'))
    } finally {
      setIsLoadingList(false)
    }
  }

  async function refreshSelectedTask(taskId = selectedTaskId) {
    if (!taskId) {
      return
    }
    setIsLoadingDetail(true)
    setErrorMessage('')

    try {
      const detail = await getMissionTask(taskId)
      setSelectedTask(detail)
      setSelectedTaskId(detail.id)
      void loadTaskArtifacts(detail.request_ids)
    } catch (error) {
      setErrorMessage(formatError(error, '加载任务详情失败'))
    } finally {
      setIsLoadingDetail(false)
    }
  }

  async function loadTaskArtifacts(requestIds: string[]) {
    const uniqueRequestIds = Array.from(new Set(requestIds)).filter(Boolean).slice(0, 5)
    if (uniqueRequestIds.length === 0) {
      setHistoryByRequestId({})
      setComposedByRequestId({})
      return
    }

    const histories = await Promise.allSettled(
      uniqueRequestIds.map(async (requestId) => [requestId, await getCruiseHistory(requestId)] as const),
    )
    const composed = await Promise.allSettled(
      uniqueRequestIds.map(async (requestId) => [requestId, await getCruiseHistoryComposed(requestId)] as const),
    )

    setHistoryByRequestId(
      Object.fromEntries(histories.flatMap((item) => (item.status === 'fulfilled' ? [item.value] : []))),
    )
    setComposedByRequestId(
      Object.fromEntries(composed.flatMap((item) => (item.status === 'fulfilled' ? [item.value] : []))),
    )
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await loadTasks(1, keyword, statusFilter)
  }

  async function handleCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmitting(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const created = await createMissionTask({
        title: form.title.trim(),
        purpose: cleanText(form.purpose),
        location: cleanText(form.location),
        date: cleanText(form.date),
        start_time: cleanText(form.start_time),
        end_time: cleanText(form.end_time),
        task_type: form.task_type,
        candidate_locations: splitCsv(form.candidate_locations),
      })
      setForm(initialForm)
      setLastAction({ kind: 'task', result: created })
      setSuccessMessage('任务单已创建')
      await loadTasks(1, keyword, statusFilter)
      await refreshSelectedTask(created.id)
    } catch (error) {
      setErrorMessage(formatError(error, '创建任务失败'))
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleSelectTask(taskId: string) {
    setSelectedTaskId(taskId)
    setLastAction(null)
    await refreshSelectedTask(taskId)
  }

  async function runTaskAction(action: string, callback: () => Promise<LastAction>) {
    if (!selectedTask) {
      return
    }
    setRunningAction(action)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const result = await callback()
      setLastAction(result)
      setSuccessMessage(actionSuccessText(action))
      await refreshSelectedTask(selectedTask.id)
      await loadTasks(page, keyword, statusFilter)
    } catch (error) {
      setErrorMessage(formatError(error, actionSuccessText(action, true)))
    } finally {
      setRunningAction('')
    }
  }

  function canRunSchedulingAction(task: MissionTaskDetailResponse | null) {
    return Boolean(task && !['completed', 'cancelled'].includes(task.status))
  }

  function canComplete(task: MissionTaskDetailResponse | null) {
    return Boolean(task && ['scheduled', 'recheck'].includes(task.status))
  }

  function canCancel(task: MissionTaskDetailResponse | null) {
    return Boolean(task && !['completed', 'cancelled'].includes(task.status))
  }

  return (
    <section className="page-card mission-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Mission Task Console</p>
          <h2>任务单管理</h2>
          <p>
            通过 <code>/tasks</code> 系列接口管理低空作业任务，把评估、推荐、窗口选择、
            执行前复核、历史快照和 Trace 聚合到同一个任务上下文里。
          </p>
        </div>
      </div>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}
      {successMessage ? <div className="success-panel">{successMessage}</div> : null}

      <div className="mission-layout">
        <section className="result-section mission-list-panel">
          <div className="section-heading-row">
            <h3>任务列表</h3>
            <span>
              共 {total} 条 / 第 {page} 页
            </span>
          </div>

          <form className="agent-form mission-filter-form" onSubmit={handleSearch}>
            <label>
              <span>关键词</span>
              <input
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                placeholder="按标题或目的检索"
              />
            </label>
            <label>
              <span>状态</span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as MissionTaskStatus | '')}
              >
                {statusOptions.map((option) => (
                  <option key={option.value || 'all'} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-actions">
              <button type="submit" disabled={isLoadingList}>
                {isLoadingList ? '加载中...' : '筛选'}
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setKeyword('')
                  setStatusFilter('')
                  void loadTasks(1, '', '')
                }}
              >
                清空
              </button>
            </div>
          </form>

          {isLoadingList ? <div className="loading-panel">正在加载任务列表...</div> : null}
          {!isLoadingList && tasks.length === 0 ? (
            <div className="empty-panel">暂无任务单。可以先创建一个任务，或通过 Agent 自然语言创建。</div>
          ) : null}

          <div className="mission-list">
            {tasks.map((task) => (
              <button
                key={task.id}
                type="button"
                className={selectedTaskId === task.id ? 'mission-item active' : 'mission-item'}
                onClick={() => void handleSelectTask(task.id)}
              >
                <div>
                  <strong>{task.title}</strong>
                  <span className={`mission-status status-${task.status}`}>{formatStatus(task.status)}</span>
                </div>
                <span>{[task.location, task.date, task.task_type].filter(Boolean).join(' / ') || '-'}</span>
                <small>
                  latest: {task.latest_decision ?? '-'} / updated: {formatDateTime(task.updated_at)}
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

        <section className="result-section mission-create-panel">
          <h3>新建任务</h3>
          <form className="agent-form" onSubmit={handleCreateTask}>
            <label>
              <span>标题</span>
              <input
                required
                value={form.title}
                onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                placeholder="深圳湾下午巡检"
              />
            </label>
            <div className="form-grid">
              <label>
                <span>地点</span>
                <input
                  value={form.location}
                  onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))}
                  placeholder="深圳湾"
                />
              </label>
              <label>
                <span>日期</span>
                <input
                  type="date"
                  value={form.date}
                  onChange={(event) => setForm((current) => ({ ...current, date: event.target.value }))}
                />
              </label>
              <label>
                <span>开始时间</span>
                <input
                  value={form.start_time}
                  onChange={(event) => setForm((current) => ({ ...current, start_time: event.target.value }))}
                  placeholder="13:00"
                />
              </label>
              <label>
                <span>结束时间</span>
                <input
                  value={form.end_time}
                  onChange={(event) => setForm((current) => ({ ...current, end_time: event.target.value }))}
                  placeholder="18:00"
                />
              </label>
              <label>
                <span>任务类型</span>
                <select
                  value={form.task_type}
                  onChange={(event) => setForm((current) => ({ ...current, task_type: event.target.value as TaskType }))}
                >
                  {taskTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>候选地点</span>
                <input
                  value={form.candidate_locations}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, candidate_locations: event.target.value }))
                  }
                  placeholder="广州塔, 佛山"
                />
              </label>
            </div>
            <label>
              <span>目的</span>
              <textarea
                rows={3}
                value={form.purpose}
                onChange={(event) => setForm((current) => ({ ...current, purpose: event.target.value }))}
                placeholder="任务背景、作业目标或调度说明"
              />
            </label>
            <div className="form-actions">
              <button type="submit" disabled={isSubmitting}>
                {isSubmitting ? '创建中...' : '创建任务单'}
              </button>
            </div>
          </form>
        </section>
      </div>

      <section className="result-section mission-detail-panel">
        <div className="section-heading-row">
          <h3>任务详情</h3>
          {selectedTask ? <span>{selectedTask.id}</span> : null}
        </div>

        {isLoadingDetail ? <div className="loading-panel">正在加载任务详情...</div> : null}
        {!selectedTask && !isLoadingDetail ? (
          <div className="empty-panel">从任务列表选择一条任务后查看详情和可执行操作。</div>
        ) : null}

        {selectedTask ? (
          <>
            <div className="decision-card caution mission-hero-card">
              <div>
                <span>当前状态</span>
                <strong>{formatStatus(selectedTask.status)}</strong>
                <p>{selectedTask.title}</p>
              </div>
              <div>
                <span>最近结论</span>
                <strong>{selectedTask.latest_decision ?? '-'}</strong>
                <p>request: {selectedTask.latest_request_id ?? '-'}</p>
              </div>
            </div>

            <div className="summary-grid mission-summary-grid">
              <SummaryItem label="地点" value={selectedTask.location} />
              <SummaryItem label="任务类型" value={selectedTask.task_type} />
              <SummaryItem label="计划日期" value={selectedTask.date} />
              <SummaryItem label="计划时间" value={`${selectedTask.start_time ?? '-'} - ${selectedTask.end_time ?? '-'}`} />
              <SummaryItem label="创建时间" value={formatDateTime(selectedTask.created_at)} />
              <SummaryItem label="更新时间" value={formatDateTime(selectedTask.updated_at)} />
            </div>

            <div className="mission-action-row">
              <button
                type="button"
                disabled={!canRunSchedulingAction(selectedTask) || runningAction === 'evaluate'}
                onClick={() =>
                  void runTaskAction('evaluate', async () => ({
                    kind: 'evaluation',
                    result: await evaluateMissionTask(selectedTask.id),
                  }))
                }
              >
                {runningAction === 'evaluate' ? '评估中...' : '评估'}
              </button>
              <button
                type="button"
                disabled={!canRunSchedulingAction(selectedTask) || runningAction === 'recommend'}
                onClick={() =>
                  void runTaskAction('recommend', async () => ({
                    kind: 'recommendation',
                    result: await recommendMissionTaskWindows(selectedTask.id),
                  }))
                }
              >
                {runningAction === 'recommend' ? '推荐中...' : '推荐窗口'}
              </button>
              <button
                type="button"
                disabled={!canRunSchedulingAction(selectedTask) || runningAction === 'preflight'}
                onClick={() =>
                  void runTaskAction('preflight', async () => ({
                    kind: 'evaluation',
                    result: await preflightCheckMissionTask(selectedTask.id),
                  }))
                }
              >
                {runningAction === 'preflight' ? '复核中...' : '执行前复核'}
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={!canComplete(selectedTask) || runningAction === 'complete'}
                onClick={() =>
                  void runTaskAction('complete', async () => ({
                    kind: 'task',
                    result: await updateMissionTaskStatus(selectedTask.id, 'completed'),
                  }))
                }
              >
                完成
              </button>
              <button
                type="button"
                className="secondary-button danger-button"
                disabled={!canCancel(selectedTask) || runningAction === 'cancel'}
                onClick={() =>
                  void runTaskAction('cancel', async () => ({
                    kind: 'task',
                    result: await updateMissionTaskStatus(selectedTask.id, 'cancelled'),
                  }))
                }
              >
                取消
              </button>
            </div>

            <section className="result-section mission-window-panel">
              <h3>推荐窗口与已选窗口</h3>
              {selectedTask.selected_window ? (
                <div className="selected-window-panel">
                  <strong>已选窗口</strong>
                  <p>
                    {String(selectedTask.selected_window.start_time ?? '-')} -{' '}
                    {String(selectedTask.selected_window.end_time ?? '-')}
                  </p>
                  <small>rank: {String(selectedTask.selected_window.rank ?? '-')}</small>
                </div>
              ) : (
                <div className="empty-panel">当前任务尚未选择执行窗口。</div>
              )}

              {recommendedWindows.length ? (
                <div className="window-list">
                  {recommendedWindows.map((window) => (
                    <article key={`${window.rank}-${window.start_time}`} className="window-card">
                      <div className="window-card-header">
                        <span className="rank-badge">#{window.rank}</span>
                        <div>
                          <strong>
                            {window.start_time} - {window.end_time}
                          </strong>
                          <p>
                            {window.overall_decision} / {window.duration_hours}h / score {window.risk_score}
                          </p>
                        </div>
                        <button
                          type="button"
                          disabled={!canRunSchedulingAction(selectedTask) || runningAction === `select-${window.rank}`}
                          onClick={() =>
                            void runTaskAction(`select-${window.rank}`, async () => ({
                              kind: 'task',
                              result: await selectMissionTaskWindow(selectedTask.id, { rank: window.rank }),
                            }))
                          }
                        >
                          选择
                        </button>
                      </div>
                      {window.reasons.length ? (
                        <div className="window-reasons">
                          <span>原因</span>
                          <ul>
                            {window.reasons.map((reason) => (
                              <li key={reason}>{reason}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-panel">暂无推荐窗口。点击“推荐窗口”后会在这里展示候选结果。</div>
              )}
            </section>

            <section className="result-section mission-linked-panel">
              <h3>关联对话、评估快照与 Trace</h3>
              <div className="mission-linked-grid">
                <LinkedList title="conversation_ids" items={selectedTask.conversation_ids} />
                <LinkedList title="request_ids" items={selectedTask.request_ids} />
                <LinkedList title="trace_ids" items={selectedTask.trace_ids} />
              </div>
              <TraceTimeline traceId={selectedTask.latest_trace_id || selectedTask.trace_ids[0]} />
            </section>

            <section className="result-section mission-artifact-panel">
              <h3>历史评估快照、规则快照与 RAG evidence</h3>
              {selectedTask.request_ids.length === 0 ? (
                <div className="empty-panel">暂无评估快照。执行评估、推荐或复核后会在这里聚合展示。</div>
              ) : null}
              <div className="mission-artifact-list">
                {selectedTask.request_ids.slice(0, 5).map((requestId) => {
                  const history = historyByRequestId[requestId]
                  const composed = composedByRequestId[requestId]
                  return (
                    <article key={requestId} className="mission-artifact-card">
                      <div className="section-heading-row">
                        <h3>request_id: {requestId}</h3>
                        <span>{history?.created_at ? formatDateTime(history.created_at) : '未加载'}</span>
                      </div>
                      {history ? (
                        <div className="summary-grid">
                          <SummaryItem label="结论" value={history.advice.overall_decision} />
                          <SummaryItem label="地点" value={String(history.request.location ?? '-')} />
                          <SummaryItem label="日期" value={String(history.request.date ?? '-')} />
                        </div>
                      ) : (
                        <div className="empty-panel">该 request_id 暂无可读取的历史评估详情。</div>
                      )}
                      {composed ? <KnowledgeAdvicePanel details={composed.details} /> : null}
                      <JsonDetails
                        title="评估快照 JSON"
                        data={history as unknown as Record<string, JsonValue>}
                      />
                      <JsonDetails
                        title="规则与 RAG 聚合 JSON"
                        data={composed as unknown as Record<string, JsonValue>}
                      />
                    </article>
                  )
                })}
              </div>
            </section>

            <JsonDetails title="任务详情 JSON" data={selectedTask as unknown as Record<string, JsonValue>} />
            <JsonDetails title="最近操作结果 JSON" data={lastAction?.result as unknown as Record<string, JsonValue>} />
          </>
        ) : null}
      </section>
    </section>
  )
}

function SummaryItem({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value || '-'}</strong>
    </div>
  )
}

function LinkedList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="linked-list-card">
      <strong>{title}</strong>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>
              <code>{item}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p>暂无关联记录</p>
      )}
    </div>
  )
}

function readLatestRecommendation(metadata?: Record<string, JsonValue>): RecommendationResponse | null {
  const value = metadata?.latest_recommendation
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  const candidate = value as unknown as RecommendationResponse
  return candidate.recommendation?.recommended_windows ? candidate : null
}

function formatStatus(status: MissionTaskStatus) {
  const labels: Record<MissionTaskStatus, string> = {
    draft: '草稿',
    evaluated: '已评估',
    scheduled: '已排期',
    recheck: '已复核',
    completed: '已完成',
    cancelled: '已取消',
  }
  return labels[status] ?? status
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

function cleanText(value: string) {
  const text = value.trim()
  return text || undefined
}

function splitCsv(value: string) {
  return value
    .split(/[,，、]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function actionSuccessText(action: string, failed = false) {
  const prefix = failed ? '' : '已'
  const labels: Record<string, string> = {
    evaluate: `${prefix}完成评估`,
    recommend: `${prefix}完成窗口推荐`,
    preflight: `${prefix}完成执行前复核`,
    complete: `${prefix}标记完成`,
    cancel: `${prefix}取消任务`,
  }
  if (action.startsWith('select-')) {
    return failed ? '选择窗口失败' : '已选择窗口'
  }
  return failed ? `${labels[action] ?? '操作'}失败` : labels[action] ?? '操作完成'
}

function formatError(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}
