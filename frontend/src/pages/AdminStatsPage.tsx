import { useEffect, useState } from 'react'
import { getAdminTaskStats } from '../api/admin'
import type { AdminTaskStats } from '../types/admin'

const statLabels: Array<{ key: keyof AdminTaskStats; label: string }> = [
  { key: 'total_tasks', label: '任务总量' },
  { key: 'successful_tasks', label: '成功任务' },
  { key: 'failed_tasks', label: '失败任务' },
  { key: 'high_risk_tasks', label: '高风险任务' },
  { key: 'rule_rejected_tasks', label: '规则拒绝' },
  { key: 'parser_failed_tasks', label: '解析失败' },
  { key: 'total_users', label: '用户总数' },
  { key: 'active_users', label: '启用用户' },
  { key: 'disabled_users', label: '禁用用户' },
  { key: 'admin_users', label: '管理员数' },
]

export function AdminStatsPage() {
  const [stats, setStats] = useState<AdminTaskStats | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    async function loadStats() {
      setIsLoading(true)
      setErrorMessage('')
      try {
        setStats(await getAdminTaskStats())
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : '加载管理员统计失败')
      } finally {
        setIsLoading(false)
      }
    }

    void loadStats()
  }, [])

  return (
    <section className="page-card admin-page">
      <div className="page-header">
        <div>
          <h2>管理员统计看板</h2>
          <p>汇总用户规模、任务执行、风险和解析失败情况，用于快速判断系统运行状态。</p>
        </div>
      </div>

      {isLoading ? <div className="loading-panel">正在加载统计数据...</div> : null}
      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}

      {stats ? (
        <div className="admin-stats-grid">
          {statLabels.map((item) => (
            <div key={item.key} className="admin-stat-card">
              <span>{item.label}</span>
              <strong>{stats[item.key]}</strong>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}
