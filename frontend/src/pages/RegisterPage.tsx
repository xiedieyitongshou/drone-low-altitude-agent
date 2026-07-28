import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

export function RegisterPage() {
  const navigate = useNavigate()
  const { isAuthenticated, register } = useAuth()
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (isAuthenticated) {
    return <Navigate to="/agent" replace />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setErrorMessage(null)

    if (password !== confirmPassword) {
      setErrorMessage('两次输入的密码不一致')
      return
    }

    setIsSubmitting(true)
    try {
      await register({
        username: username.trim(),
        password,
        display_name: displayName.trim() || null,
      })
      navigate('/agent', { replace: true })
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '注册失败')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <section className="page-card auth-page">
      <div className="page-header">
        <div>
          <p className="eyebrow">Authentication</p>
          <h2>注册账号</h2>
          <p>注册后会自动登录，并进入 Agent 页面。</p>
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
          <span>展示名称</span>
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            autoComplete="nickname"
            placeholder="可选"
          />
        </label>

        <label>
          <span>密码</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
            placeholder="至少 8 位"
          />
        </label>

        <label>
          <span>确认密码</span>
          <input
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            minLength={8}
            required
            autoComplete="new-password"
            placeholder="再次输入密码"
          />
        </label>

        {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

        <div className="form-actions">
          <button type="submit" disabled={isSubmitting}>
            {isSubmitting ? '正在注册...' : '注册并登录'}
          </button>
          <Link className="secondary-link" to="/login">
            已有账号？去登录
          </Link>
        </div>
      </form>
    </section>
  )
}
