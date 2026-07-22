import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { evaluateCruise } from '../api/evaluation'
import { JsonDetails } from '../components/JsonDetails'
import type {
  CruiseAssessmentResponse,
  CruiseEvaluateRequest,
  TaskType,
} from '../types/evaluation'

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

function getDecisionClass(decision?: string) {
  if (decision === '适飞') {
    return 'suitable'
  }

  if (decision === '禁飞') {
    return 'prohibited'
  }

  return 'caution'
}

function formatWeatherValue(value?: string | null, suffix = '') {
  return value ? `${value}${suffix}` : '-'
}

export function EvaluatePage() {
  const [form, setForm] = useState<CruiseEvaluateRequest>({
    location: 'Shenzhen',
    date: getTomorrowDate(),
    start_time: '14:00',
    end_time: '17:00',
    task_type: 'cruise',
    purpose: '日常巡航任务',
  })
  const [result, setResult] = useState<CruiseAssessmentResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const requestId = useMemo(() => {
    const value = result?.request?.request_id
    return typeof value === 'string' ? value : '-'
  }, [result])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setIsSubmitting(true)
    setErrorMessage('')
    setResult(null)

    try {
      const response = await evaluateCruise({
        ...form,
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
    <section className="page-card evaluate-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Day 38</p>
          <h2>单地点评估</h2>
          <p>
            该页面调用 <code>/cruise/evaluate</code>
            ，展示规则引擎对指定地点、日期和时间段的确定性评估结果。
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
            {isSubmitting ? '评估中...' : '开始评估'}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() =>
              setForm((current) => ({
                ...current,
                start_time: '09:00',
                end_time: '12:00',
              }))
            }
          >
            上午三小时
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={() =>
              setForm((current) => ({
                ...current,
                start_time: '22:00',
                end_time: '24:00',
              }))
            }
          >
            测试 24:00
          </button>
        </div>
      </form>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

      {result ? (
        <div className="evaluation-result">
          <div
            className={`decision-card ${getDecisionClass(
              result.advice.overall_decision,
            )}`}
          >
            <div>
              <span>整体结论</span>
              <strong>{result.advice.overall_decision}</strong>
              <p>{result.advice.allow_cruise ? '当前任务允许执行' : '当前任务不建议执行'}</p>
            </div>
            <div>
              <span>request_id</span>
              <code>{requestId}</code>
            </div>
          </div>

          <div className="summary-grid">
            <div>
              <span>地点</span>
              <strong>{result.weather?.location?.name ?? form.location}</strong>
            </div>
            <div>
              <span>评估小时数</span>
              <strong>{result.advice.hourly_assessment.length}</strong>
            </div>
            <div>
              <span>天气预警</span>
              <strong>{result.warnings?.warning_count ?? 0}</strong>
            </div>
          </div>

          <section className="result-section">
            <h3>风险原因</h3>
            {result.advice.summary_risk_factors.length > 0 ? (
              <ul className="risk-list">
                {result.advice.summary_risk_factors.map((factor) => (
                  <li key={factor}>{factor}</li>
                ))}
              </ul>
            ) : (
              <div className="empty-panel">当前时间段未发现明显风险原因。</div>
            )}
          </section>

          <section className="result-section">
            <h3>逐小时评估</h3>
            <div className="hourly-table-wrap">
              <table className="hourly-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>结论</th>
                    <th>天气</th>
                    <th>温度</th>
                    <th>风力</th>
                    <th>降水</th>
                    <th>降水概率</th>
                    <th>风险原因</th>
                  </tr>
                </thead>
                <tbody>
                  {result.advice.hourly_assessment.map((item) => (
                    <tr key={item.fx_time}>
                      <td>{item.fx_time}</td>
                      <td>
                        <span
                          className={`decision-pill ${getDecisionClass(
                            item.decision,
                          )}`}
                        >
                          {item.decision}
                        </span>
                      </td>
                      <td>{item.weather.text ?? '-'}</td>
                      <td>{formatWeatherValue(item.weather.temp, '℃')}</td>
                      <td>{formatWeatherValue(item.weather.wind_scale, '级')}</td>
                      <td>{formatWeatherValue(item.weather.precip, 'mm')}</td>
                      <td>{formatWeatherValue(item.weather.pop, '%')}</td>
                      <td>
                        {item.risk_factors.length > 0
                          ? item.risk_factors.join('；')
                          : '无明显风险'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="result-section">
            <h3>天气预警</h3>
            {result.warnings?.has_warning ? (
              <div className="warning-list">
                {result.warnings.warnings.map((warning, index) => (
                  <article className="warning-card" key={warning.warning_id ?? index}>
                    <strong>{warning.title ?? warning.event_type ?? '未知预警'}</strong>
                    <p>
                      {warning.warning_level ?? '-'} / {warning.status ?? '-'} /{' '}
                      {warning.publish_time ?? '-'}
                    </p>
                    <p>{warning.text ?? '暂无详细说明'}</p>
                  </article>
                ))}
              </div>
            ) : (
              <div className="empty-panel">当前地点未返回天气预警。</div>
            )}
          </section>

          <JsonDetails
            title="完整评估响应 JSON"
            data={result as unknown as Record<string, never>}
          />
        </div>
      ) : null}
    </section>
  )
}
