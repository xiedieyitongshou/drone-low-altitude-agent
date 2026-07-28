import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

interface LocationState {
  from?: {
    pathname?: string
  }
}

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated, login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const from = (location.state as LocationState | null)?.from?.pathname ?? '/agent'

  if (isAuthenticated) {
    return <Navigate to={from} replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage(null)
    setIsSubmitting(true)

    try {
      await login({ username: username.trim(), password })
      navigate(from, { replace: true })
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '登录失败')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="page-card auth-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Authentication</p>
          <h2>登录账号</h2>
          <p>登录后才能调用 Agent、查看历史记录和维护个人 Profile。</p>
        </div>
      </div>

      <form className="agent-form auth-form" onSubmit={handleSubmit}>
        <label>
          <span>用户名</span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            minLength={3}
            required
            autoComplete="username"
            placeholder="demo"
          />
        </label>

        <label>
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            autoComplete="current-password"
            placeholder="请输入密码"
          />
        </label>

        {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

        <div className="form-actions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? '正在登录...' : '登录'}
          </button>
          <Link className="secondary-link" to="/register">
            还没有账号？去注册
          </Link>
        </div>
      </form>
    </section>
  )
}
