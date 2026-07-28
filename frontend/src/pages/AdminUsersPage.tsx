import { useEffect, useState } from 'react'
import {
  listAdminUsers,
  updateAdminUserRole,
  updateAdminUserStatus,
} from '../api/admin'
import type { AdminUser } from '../types/admin'

export function AdminUsersPage() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [username, setUsername] = useState('')
  const [role, setRole] = useState<'user' | 'admin' | ''>('')
  const [isActive, setIsActive] = useState<boolean | ''>('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    void loadUsers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  async function loadUsers(nextPage = page) {
    setIsLoading(true)
    setErrorMessage('')
    try {
      const response = await listAdminUsers({
        page: nextPage,
        page_size: 10,
        username: username.trim() || undefined,
        role,
        is_active: isActive,
      })
      setUsers(response.items)
      setTotal(response.total)
      setPage(response.page)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载用户列表失败')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleStatusChange(user: AdminUser) {
    setSuccessMessage('')
    setErrorMessage('')
    try {
      const updated = await updateAdminUserStatus(user.id, !user.is_active)
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setSuccessMessage('用户状态已更新。')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '更新用户状态失败')
    }
  }

  async function handleRoleChange(user: AdminUser) {
    setSuccessMessage('')
    setErrorMessage('')
    try {
      const nextRole = user.role === 'admin' ? 'user' : 'admin'
      const updated = await updateAdminUserRole(user.id, nextRole)
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setSuccessMessage('用户角色已更新。')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '更新用户角色失败')
    }
  }

  const totalPages = Math.max(Math.ceil(total / 10), 1)

  return (
    <section className="page-card admin-page">
      <div className="page-header">
        <div>
          <h2>管理员用户管理</h2>
          <p>管理员可以查看用户列表、启停账号，并在受保护边界内调整普通用户和管理员角色。</p>
        </div>
      </div>

      <form
        className="agent-form admin-filter-form"
        onSubmit={(event) => {
          event.preventDefault()
          void loadUsers(1)
        }}
      >
        <label>
          <span>用户名</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label>
          <span>角色</span>
          <select value={role} onChange={(event) => setRole(event.target.value as 'user' | 'admin' | '')}>
            <option value="">全部</option>
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <label>
          <span>状态</span>
          <select
            value={isActive === '' ? '' : String(isActive)}
            onChange={(event) => {
              const value = event.target.value
              setIsActive(value === '' ? '' : value === 'true')
            }}
          >
            <option value="">全部</option>
            <option value="true">启用</option>
            <option value="false">禁用</option>
          </select>
        </label>
        <div className="form-actions">
          <button type="submit" disabled={isLoading}>
            {isLoading ? '查询中...' : '查询用户'}
          </button>
        </div>
      </form>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}
      {successMessage ? <div className="success-panel">{successMessage}</div> : null}

      <div className="admin-table-wrapper">
        <table className="admin-table">
          <thead>
            <tr>
              <th>用户名</th>
              <th>展示名</th>
              <th>角色</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.username}</td>
                <td>{user.display_name ?? '-'}</td>
                <td>{user.role}</td>
                <td>{user.is_active ? '启用' : '禁用'}</td>
                <td>{user.created_at}</td>
                <td>
                  <div className="admin-action-row">
                    <button type="button" className="secondary-button" onClick={() => void handleStatusChange(user)}>
                      {user.is_active ? '禁用' : '启用'}
                    </button>
                    <button type="button" className="secondary-button" onClick={() => void handleRoleChange(user)}>
                      {user.role === 'admin' ? '降为 user' : '升为 admin'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="pagination-row">
        <button
          type="button"
          className="secondary-button"
          disabled={page <= 1 || isLoading}
          onClick={() => setPage((current) => Math.max(current - 1, 1))}
        >
          上一页
        </button>
        <span>
          共 {total} 条 / {page} / {totalPages}
        </span>
        <button
          type="button"
          className="secondary-button"
          disabled={page >= totalPages || isLoading}
          onClick={() => setPage((current) => current + 1)}
        >
          下一页
        </button>
      </div>
    </section>
  )
}
