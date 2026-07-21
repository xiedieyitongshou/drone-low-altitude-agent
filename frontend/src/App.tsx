import { NavLink, Route, Routes } from 'react-router-dom'
import { HealthPage } from './pages/HealthPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import './App.css'

const navItems = [
  { to: '/', label: '系统状态' },
  { to: '/agent', label: 'Agent 对话' },
  { to: '/evaluate', label: '单地点评估' },
  { to: '/recommend', label: '推荐窗口' },
  { to: '/compare', label: '多地点比选' },
  { to: '/history', label: '历史记录' },
]

function App() {
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
              className={({ isActive }) =>
                isActive ? 'nav-link active' : 'nav-link'
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="main-panel">
        <Routes>
          <Route path="/" element={<HealthPage />} />
          <Route
            path="/agent"
            element={
              <PlaceholderPage
                title="Agent 对话"
                description="后续接入 /agent/query，用自然语言完成任务解析、评估、推荐和总结。"
              />
            }
          />
          <Route
            path="/evaluate"
            element={
              <PlaceholderPage
                title="单地点评估"
                description="后续接入 /cruise/evaluate，展示逐小时风险判断和整体结论。"
              />
            }
          />
          <Route
            path="/recommend"
            element={
              <PlaceholderPage
                title="推荐窗口"
                description="后续接入推荐接口，展示适飞时间窗口、风险原因和排序依据。"
              />
            }
          />
          <Route
            path="/compare"
            element={
              <PlaceholderPage
                title="多地点比选"
                description="后续接入多地点比选接口，展示地点风险排行和 TopK 推荐。"
              />
            }
          />
          <Route
            path="/history"
            element={
              <PlaceholderPage
                title="历史记录"
                description="后续接入历史查询接口，展示历史评估、推荐和对话记录摘要。"
              />
            }
          />
        </Routes>
      </main>
    </div>
  )
}

export default App
