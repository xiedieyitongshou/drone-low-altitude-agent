import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../auth/useAuth'
import type { UserRole } from '../types/auth'

export function ProtectedRoute({
  children,
  requiredRole,
}: {
  children: ReactNode
  requiredRole?: UserRole
}) {
  const location = useLocation()
  const { isAuthenticated, isLoading, user } = useAuth()

  if (isLoading) {
    return <div className="empty-panel">正在恢复登录状态...</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (requiredRole && user?.role !== requiredRole && user?.role !== 'super_admin') {
    return <div className="error-panel">当前账号没有访问该页面的权限。</div>
  }

  return children
}
