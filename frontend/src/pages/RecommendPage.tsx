import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { recommendExecutionWindows } from '../api/recommendation'
import { JsonDetails } from '../components/JsonDetails'
import type { TaskType } from '../types/evaluation'
import type {
  RecommendationRequest,
  RecommendationResponse,
} from '../types/recommendation'

const taskTypeOptions: Array<{ value: TaskType; label: string }> = [
  { value: 'cruise', label: '日常巡航' },
  { value: 'inspection', label: '巡检任务' },
  { value: 'hover', label: '悬停拍摄' },
  { value: 'survey', label: '测绘任务' },
]

function getTodayDate() {
  return new Date().toISOString().slice(0, 10)
}

function getDecisionClass(decision?: string) {
  if (decision === '适飞') {
    return 'suitable'
  }

  if (decision === '禁飞') {
    return 'prohibited'
  }

  return 'caution'
}

export function RecommendPage() {
  const [form, setForm] = useState<RecommendationRequest>({
    location: 'Shenzhen',
    date: getTodayDate(),
    task_type: 'cruise',
    purpose: '日常巡航任务',
    scan_hours: 72,
    min_window_hours: 2,
  })
  const [result, setResult] = useState<RecommendationResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const windows = result?.recommendation.recommended_windows ?? []
  const topWindow = windows[0]
  const noWindowMessage = useMemo(() => {
    if (!result || windows.length > 0) {
      return ''
    }

    return `未来 ${result.request.scan_hours ?? form.scan_hours} 小时内，未发现满足最小时长 ${result.recommendation.strategy.min_window_hours} 小时的低风险窗口。`
  }, [form.scan_hours, result, windows.length])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmitting(true)
    setErrorMessage('')
    setResult(null)

    try {
      const response = await recommendExecutionWindows({
        ...form,
        scan_hours: Number(form.scan_hours),
        min_window_hours: Number(form.min_window_hours),
        purpose: form.purpose?.trim() || null,
      })
      setResult(response)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '请求失败')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="page-card recommend-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Day 39</p>
          <h2>推荐执行窗口</h2>
          <p>
            该页面调用 <code>/cruise/recommend</code>
            ，用于回答“什么时候最适合执行任务”。
          </p>
        </div>
      </div>

      <form className="agent-form" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label>
            <span>地点</span>
            <input
              value={form.location}
              onChange={(event) =>
                setForm((current) => ({ ...current, location: event.target.value }))
              }
              placeholder="例如：Shenzhen / 深圳"
              required
            />
          </label>
          <label>
            <span>起始日期</span>
            <input
              type="date"
              value={form.date}
              onChange={(event) =>
                setForm((current) => ({ ...current, date: event.target.value }))
              }
              required
            />
          </label>
          <label>
            <span>任务类型</span>
            <select
              value={form.task_type}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  task_type: event.target.value as TaskType,
                }))
              }
            >
              {taskTypeOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}（{item.value}）
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>任务目的</span>
            <input
              value={form.purpose ?? ''}
              onChange={(event) =>
                setForm((current) => ({ ...current, purpose: event.target.value }))
              }
              placeholder="可选"
            />
          </label>
          <label>
            <span>扫描小时数</span>
            <input
              type="number"
              min={1}
              max={168}
              value={form.scan_hours}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  scan_hours: Number(event.target.value),
                }))
              }
            />
          </label>
          <label>
            <span>最小窗口小时数</span>
            <input
              type="number"
              min={1}
              max={24}
              value={form.min_window_hours}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  min_window_hours: Number(event.target.value),
                }))
              }
            />
          </label>
        </div>

        <div className="form-actions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? '推荐中...' : '生成推荐'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() =>
              setForm((current) => ({
                ...current,
                scan_hours: 72,
                min_window_hours: 2,
              }))
            }
          >
            未来 72 小时
          </button>
        </div>
      </form>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

      {result ? (
        <div className="recommendation-result">
          <div className="summary-grid">
            <div>
              <span>候选窗口数</span>
              <strong>{result.recommendation.total_candidates}</strong>
            </div>
            <div>
              <span>推荐窗口数</span>
              <strong>{windows.length}</strong>
            </div>
            <div>
              <span>最小连续时长</span>
              <strong>{result.recommendation.strategy.min_window_hours} 小时</strong>
            </div>
          </div>

          {topWindow ? (
            <div className={`decision-card ${getDecisionClass(topWindow.overall_decision)}`}>
              <div>
                <span>第一推荐窗口</span>
                <strong>{topWindow.overall_decision}</strong>
                <p>
                  {topWindow.start_time} 至 {topWindow.end_time}，连续{' '}
                  {topWindow.duration_hours} 小时
                </p>
              </div>
              <div>
                <span>风险分数</span>
                <strong>{topWindow.risk_score}</strong>
              </div>
            </div>
          ) : (
            <div className="empty-panel">{noWindowMessage}</div>
          )}

          {windows.length > 0 ? (
            <section className="result-section">
              <h3>推荐窗口列表</h3>
              <div className="window-list">
                {windows.map((window) => (
                  <article className="window-card" key={`${window.rank}-${window.start_time}`}>
                    <div className="window-card-header">
                      <span className="rank-badge">#{window.rank}</span>
                      <div>
                        <strong>
                          {window.start_time} 至 {window.end_time}
                        </strong>
                        <p>
                          {window.duration_hours} 小时 / 风险分数 {window.risk_score}
                        </p>
                      </div>
                      <span className={`decision-pill ${getDecisionClass(window.overall_decision)}`}>
                        {window.overall_decision}
                      </span>
                    </div>

                    <div className="window-reasons">
                      <span>推荐理由</span>
                      {window.reasons.length > 0 ? (
                        <ul>
                          {window.reasons.map((reason) => (
                            <li key={reason}>{reason}</li>
                          ))}
                        </ul>
                      ) : (
                        <p>当前窗口风险较低，未返回额外说明。</p>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <section className="result-section">
            <h3>排序策略</h3>
            {result.recommendation.strategy.sort_rules.length > 0 ? (
              <ul className="risk-list">
                {result.recommendation.strategy.sort_rules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            ) : (
              <div className="empty-panel">后端未返回排序策略说明。</div>
            )}
          </section>

          <JsonDetails
            title="完整推荐响应 JSON"
            data={result as unknown as Record<string, never>}
          />
        </div>
      ) : null}
    </section>
  )
}
