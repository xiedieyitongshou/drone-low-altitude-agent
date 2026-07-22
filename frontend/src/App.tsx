import { NavLink, Route, Routes } from 'react-router-dom'
import { AgentPage } from './pages/AgentPage'
import { ComparePage } from './pages/ComparePage'
import { EvaluatePage } from './pages/EvaluatePage'
import { HealthPage } from './pages/HealthPage'
import { HistoryPage } from './pages/HistoryPage'
import { RecommendPage } from './pages/RecommendPage'
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
          <Route path="/agent" element={<AgentPage />} />
          <Route path="/evaluate" element={<EvaluatePage />} />
          <Route path="/recommend" element={<RecommendPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
