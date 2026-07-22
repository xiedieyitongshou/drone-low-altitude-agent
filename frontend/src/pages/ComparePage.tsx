import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { compareCruiseLocations } from '../api/comparison'
import { JsonDetails } from '../components/JsonDetails'
import type {
  ComparedLocationResult,
  MultiLocationComparisonRequest,
  MultiLocationComparisonResponse,
} from '../types/comparison'
import type { TaskType } from '../types/evaluation'

const taskTypeOptions: Array<{ value: TaskType; label: string }> = [
  { value: 'cruise', label: '日常巡航' },
  { value: 'inspection', label: '巡检任务' },
  { value: 'hover', label: '悬停拍摄' },
  { value: 'survey', label: '测绘任务' },
]

function getTomorrowDate() {
  const date = new Date()
  date.setDate(date.getDate() + 1)
  return date.toISOString().slice(0, 10)
}

function getDecisionClass(decision?: string | null) {
  if (decision === '适飞') {
    return 'suitable'
  }

  if (decision === '禁飞') {
    return 'prohibited'
  }

  return 'caution'
}

function parseLocations(value: string) {
  return value
    .split(/[\n,，、]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function formatNumber(value?: number | null, digits = 1) {
  return typeof value === 'number' ? value.toFixed(digits) : '-'
}

function buildRankingReason(item: ComparedLocationResult) {
  if (!item.available) {
    return item.error_message || '该地点暂不可用，无法参与正常排序。'
  }

  const reasons = [
    `综合得分 ${formatNumber(item.score)}`,
    `可飞小时 ${item.flyable_hour_count}`,
    `最长连续可飞 ${item.max_continuous_flyable_hours} 小时`,
  ]

  if (item.earliest_flyable_time) {
    reasons.push(`最早可飞时间 ${item.earliest_flyable_time}`)
  }

  if (item.summary_risk_factors.length > 0) {
    reasons.push(`主要风险：${item.summary_risk_factors.join('；')}`)
  }

  return reasons.join('，')
}

export function ComparePage() {
  const [locationText, setLocationText] = useState('Shenzhen\nGuangzhou\nZhuhai')
  const [form, setForm] = useState<Omit<MultiLocationComparisonRequest, 'locations'>>({
    date: getTomorrowDate(),
    start_time: '14:00',
    end_time: '17:00',
    task_type: 'cruise',
    purpose: '多地点日常巡航任务',
    top_k: 3,
    comparison_mode: 'default',
  })
  const [result, setResult] = useState<MultiLocationComparisonResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const parsedLocations = useMemo(() => parseLocations(locationText), [locationText])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage('')
    setResult(null)

    if (parsedLocations.length < 2) {
      setErrorMessage('候选地点至少需要 2 个。')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await compareCruiseLocations({
        ...form,
        locations: parsedLocations,
        purpose: form.purpose?.trim() || null,
        top_k: Number(form.top_k),
      })
      setResult(response)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '请求失败')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="page-card compare-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Day 40</p>
          <h2>多地点比选</h2>
          <p>
            该页面调用 <code>/cruise/compare</code>
            ，用于回答“多个地点中先去哪一个”。
          </p>
        </div>
      </div>

      <form className="agent-form" onSubmit={handleSubmit}>
        <label className="query-box">
          <span>候选地点</span>
          <textarea
            value={locationText}
            onChange={(event) => setLocationText(event.target.value)}
            rows={4}
            placeholder="每行一个地点，也支持逗号分隔"
          />
        </label>

        <div className="form-grid">
          <label>
            <span>日期</span>
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
            <span>开始时间</span>
            <input
              type="time"
              value={form.start_time}
              onChange={(event) =>
                setForm((current) => ({ ...current, start_time: event.target.value }))
              }
              required
            />
          </label>
          <label>
            <span>结束时间</span>
            <input
              type="time"
              value={form.end_time === '24:00' ? '23:59' : form.end_time}
              onChange={(event) =>
                setForm((current) => ({ ...current, end_time: event.target.value }))
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
            <span>Top K</span>
            <input
              type="number"
              min={1}
              max={10}
              value={form.top_k}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  top_k: Number(event.target.value),
                }))
              }
            />
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
        </div>

        <div className="form-actions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? '比选中...' : '开始比选'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() => setLocationText('Shenzhen\nGuangzhou\nZhuhai')}
          >
            填入珠三角样例
          </button>
        </div>
      </form>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

      {result ? (
        <div className="comparison-result">
          {result.recommended_location ? (
            <div
              className={`decision-card ${getDecisionClass(
                result.recommended_location.overall_decision,
              )}`}
            >
              <div>
                <span>推荐地点</span>
                <strong>{result.recommended_location.location}</strong>
                <p>{buildRankingReason(result.recommended_location)}</p>
              </div>
              <div>
                <span>综合得分</span>
                <strong>{formatNumber(result.recommended_location.score)}</strong>
              </div>
            </div>
          ) : (
            <div className="empty-panel">当前没有可推荐地点，请检查地点或时间段。</div>
          )}

          <div className="summary-grid">
            <div>
              <span>候选地点</span>
              <strong>{result.comparisons.length}</strong>
            </div>
            <div>
              <span>Top K</span>
              <strong>{result.top_k_locations.length}</strong>
            </div>
            <div>
              <span>参与排序地点</span>
              <strong>{result.comparisons.filter((item) => item.available).length}</strong>
            </div>
          </div>

          <section className="result-section">
            <h3>地点排名</h3>
            <div className="comparison-list">
              {result.comparisons.map((item) => (
                <article
                  className={`comparison-card ${item.available ? '' : 'unavailable'}`}
                  key={`${item.rank}-${item.location}`}
                >
                  <div className="comparison-card-main">
                    <span className="rank-badge">#{item.rank}</span>
                    <div>
                      <strong>{item.location}</strong>
                      <p>{buildRankingReason(item)}</p>
                    </div>
                    <span className={`decision-pill ${getDecisionClass(item.overall_decision)}`}>
                      {item.overall_decision ?? '不可用'}
                    </span>
                  </div>

                  <div className="comparison-metrics">
                    <div>
                      <span>综合得分</span>
                      <strong>{formatNumber(item.score)}</strong>
                    </div>
                    <div>
                      <span>风险分数</span>
                      <strong>{item.risk_score ?? '-'}</strong>
                    </div>
                    <div>
                      <span>可飞小时数</span>
                      <strong>{item.flyable_hour_count}</strong>
                    </div>
                    <div>
                      <span>最长连续可飞</span>
                      <strong>{item.max_continuous_flyable_hours} 小时</strong>
                    </div>
                    <div>
                      <span>窗口质量</span>
                      <strong>{formatNumber(item.window_quality_score)}</strong>
                    </div>
                    <div>
                      <span>最早可飞</span>
                      <strong>{item.earliest_flyable_time ?? '-'}</strong>
                    </div>
                  </div>

                  {item.best_window ? (
                    <div className="best-window-panel">
                      最佳窗口：{item.best_window.start_time} 至 {item.best_window.end_time}
                      ，连续 {item.best_window.duration_hours} 小时，风险分数{' '}
                      {item.best_window.risk_score}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>

          <JsonDetails
            title="完整比选响应 JSON"
            data={result as unknown as Record<string, never>}
          />
        </div>
      ) : null}
    </section>
  )
}
