import { useState } from 'react'
import type { FormEvent } from 'react'
import { getCruiseHistory, getCruiseHistoryComposed } from '../api/history'
import { JsonDetails } from '../components/JsonDetails'
import type { CruiseHistoryResponse, UnifiedBusinessResponse } from '../types/history'

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
  const [requestId, setRequestId] = useState('')
  const [history, setHistory] = useState<CruiseHistoryResponse | null>(null)
  const [composed, setComposed] = useState<UnifiedBusinessResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const hasResult = Boolean(history || composed)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedRequestId = requestId.trim()

    if (!trimmedRequestId) {
      setErrorMessage('请输入 request_id。')
      return
    }

    setIsLoading(true)
    setErrorMessage('')
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
      setErrorMessage(error instanceof Error ? error.message : '查询失败')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="page-card history-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Day 41</p>
          <h2>历史查询与复盘</h2>
          <p>
            该页面同时调用 <code>/cruise/history/{'{request_id}'}</code> 和{' '}
            <code>/cruise/history/{'{request_id}'}/composed</code>
            ，展示任务从输入、判断、落库到复盘的完整链路。
          </p>
        </div>
      </div>

      <form className="agent-form history-form" onSubmit={handleSubmit}>
        <label>
          <span>request_id</span>
          <input
            value={requestId}
            onChange={(event) => setRequestId(event.target.value)}
            placeholder="从单地点评估页面复制 request_id"
          />
        </label>
        <div className="form-actions">
          <button type="submit" disabled={isLoading}>
            {isLoading ? '查询中...' : '查询历史'}
          </button>
        </div>
      </form>

      {!hasResult && !isLoading && !errorMessage ? (
        <div className="empty-panel">
          暂无历史复盘数据。请先在“单地点评估”页面完成一次评估，并复制返回的
          request_id。
        </div>
      ) : null}

      {isLoading ? <div className="loading-panel">正在查询历史记录...</div> : null}
      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

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
              <div className="response-badges">
                <span>scene: {composed.scene}</span>
                <span>source: {composed.explanation_source}</span>
                <span>llm_used: {String(composed.llm_used)}</span>
              </div>
            </section>
          ) : null}

          <section className="result-section">
            <h3>历史任务请求</h3>
            <div className="history-request-grid">
              <div>
                <span>日期</span>
                <strong>{getRequestValue(history.request, 'date')}</strong>
              </div>
              <div>
                <span>开始时间</span>
                <strong>{getRequestValue(history.request, 'start_time')}</strong>
              </div>
              <div>
                <span>结束时间</span>
                <strong>{getRequestValue(history.request, 'end_time')}</strong>
              </div>
              <div>
                <span>跨天</span>
                <strong>{String(history.request.spans_next_day ?? false)}</strong>
              </div>
            </div>
          </section>

          <section className="result-section">
            <h3>风险原因</h3>
            {history.advice.summary_risk_factors.length > 0 ? (
              <ul className="risk-list">
                {history.advice.summary_risk_factors.map((factor) => (
                  <li key={factor}>{factor}</li>
                ))}
              </ul>
            ) : (
              <div className="empty-panel">历史记录中未发现明显风险原因。</div>
            )}
          </section>

          <section className="result-section">
            <h3>逐小时评估复盘</h3>
            <div className="hourly-table-wrap">
              <table className="hourly-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>结论</th>
                    <th>天气</th>
                    <th>风力</th>
                    <th>降水</th>
                    <th>降水概率</th>
                    <th>风险原因</th>
                  </tr>
                </thead>
                <tbody>
                  {history.advice.hourly_assessment.map((item) => (
                    <tr key={item.fx_time}>
                      <td>{item.fx_time}</td>
                      <td>
                        <span className={`decision-pill ${getDecisionClass(item.decision)}`}>
                          {item.decision}
                        </span>
                      </td>
                      <td>{item.weather.text ?? '-'}</td>
                      <td>{item.weather.wind_scale ?? '-'}</td>
                      <td>{item.weather.precip ?? '-'}</td>
                      <td>{item.weather.pop ? `${item.weather.pop}%` : '-'}</td>
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
            {history.warnings?.has_warning ? (
              <div className="warning-list">
                {history.warnings.warnings.map((warning, index) => (
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
              <div className="empty-panel">历史记录中没有天气预警。</div>
            )}
          </section>

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
  )
}
