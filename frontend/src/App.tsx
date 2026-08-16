import { NavLink, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/useAuth'
import { ProtectedRoute } from './components/ProtectedRoute'
import { AdminConversationsPage } from './pages/AdminConversationsPage'
import { AdminKnowledgePage } from './pages/AdminKnowledgePage'
import { AdminStatsPage } from './pages/AdminStatsPage'
import { AdminUsersPage } from './pages/AdminUsersPage'
import { AgentPage } from './pages/AgentPage'
import { ComparePage } from './pages/ComparePage'
import { EvaluatePage } from './pages/EvaluatePage'
import { HealthPage } from './pages/HealthPage'
import { HistoryPage } from './pages/HistoryPage'
import { LoginPage } from './pages/LoginPage'
import { MissionTasksPage } from './pages/MissionTasksPage'
import { ProfilePage } from './pages/ProfilePage'
import { RecommendPage } from './pages/RecommendPage'
import { RegisterPage } from './pages/RegisterPage'
import './App.css'

const navItems = [
  { to: '/', label: '系统状态' },
  { to: '/agent', label: 'Agent 对话' },
  { to: '/evaluate', label: '单点评估' },
  { to: '/recommend', label: '推荐窗口' },
  { to: '/compare', label: '多地点比选' },
  { to: '/tasks', label: '任务单' },
  { to: '/history', label: '历史记录' },
  { to: '/profile', label: 'Profile 设置' },
]

const adminNavItems = [
  { to: '/admin', label: '管理统计' },
  { to: '/admin/users', label: '用户管理' },
  { to: '/admin/conversations', label: '任务审计' },
  { to: '/admin/knowledge', label: 'RAG 知识库' },
]

function App() {
  const { isAuthenticated, logout, user } = useAuth()
  const canViewAdmin = user?.role === 'admin' || user?.role === 'super_admin'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">UAV</span>
          <div>
            <h1>低空巡航决策系统</h1>
            <p>Drone Low Altitude Agent</p>
          </div>
        </div>

        <nav className="nav-list" aria-label="主导航">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              {item.label}
            </NavLink>
          ))}
          {canViewAdmin
            ? adminNavItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/admin'}
                  className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
                >
                  {item.label}
                </NavLink>
              ))
            : null}
        </nav>

        <div className="auth-panel">
          {isAuthenticated && user ? (
            <>
              <div>
                <span>当前用户</span>
                <strong>{user.display_name || user.username}</strong>
                <small>
                  {user.role}
                  {user.tenant_id ? ` / tenant: ${user.tenant_id}` : ''}
                </small>
              </div>
              <button type="button" className="logout-button" onClick={logout}>
                退出登录
              </button>
            </>
          ) : (
            <div>
              <span>认证状态</span>
              <strong>未登录</strong>
              <small>登录后可使用 Agent、任务单、历史记录和 Profile 能力。</small>
            </div>
          )}
        </div>
      </aside>

      <main className="main-panel">
        <Routes>
          <Route path="/" element={<HealthPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/agent"
            element={
              <ProtectedRoute>
                <AgentPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/evaluate"
            element={
              <ProtectedRoute>
                <EvaluatePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/recommend"
            element={
              <ProtectedRoute>
                <RecommendPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/compare"
            element={
              <ProtectedRoute>
                <ComparePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/tasks"
            element={
              <ProtectedRoute>
                <MissionTasksPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/history"
            element={
              <ProtectedRoute>
                <HistoryPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ProtectedRoute>
                <ProfilePage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute requiredRole="admin">
                <AdminStatsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute requiredRole="admin">
                <AdminUsersPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/conversations"
            element={
              <ProtectedRoute requiredRole="admin">
                <AdminConversationsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/knowledge"
            element={
              <ProtectedRoute requiredRole="admin">
                <AdminKnowledgePage />
              </ProtectedRoute>
            }
          />
        </Routes>
      </main>
    </div>
  )
}

export default App
