import { useEffect, useState } from 'react'
import { getHealth } from '../api/health'
import type { HealthResponse } from '../types/health'

type LoadState = 'idle' | 'loading' | 'success' | 'error'

export function HealthPage() {
  const [state, setState] = useState<LoadState>('idle')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState('')

  async function loadHealth() {
    setState('loading')
    setErrorMessage('')

    try {
      const data = await getHealth()
      setHealth(data)
      setState('success')
    } catch (error) {
      setHealth(null)
      setErrorMessage(error instanceof Error ? error.message : '请求失败')
      setState('error')
    }
  }

  useEffect(() => {
    void loadHealth()
  }, [])

  return (
    <section className="page-card">
      <div className="page-header">
        <div>
          <p className="eyebrow">Day 36</p>
          <h2>前端框架初始化</h2>
          <p>
            当前页面用于验证 React 前端已经能够请求 FastAPI 后端
            <code>/health</code> 接口。
          </p>
        </div>
        <button type="button" onClick={loadHealth} disabled={state === 'loading'}>
          {state === 'loading' ? '检测中...' : '重新检测'}
        </button>
      </div>

      <div className={`status-panel ${state}`}>
        <span className="status-dot" />
        <div>
          <strong>
            {state === 'success'
              ? '后端连接正常'
              : state === 'error'
                ? '后端连接失败'
                : '等待检测'}
          </strong>
          <p>
            {state === 'success'
              ? `服务：${health?.service}，环境：${health?.environment}`
              : state === 'error'
                ? errorMessage
                : '页面加载后会自动请求后端健康检查接口。'}
          </p>
        </div>
      </div>

      <pre className="code-block">
        {health ? JSON.stringify(health, null, 2) : '暂无后端响应数据'}
      </pre>
    </section>
  )
}
