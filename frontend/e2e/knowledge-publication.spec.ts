import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

async function openKnowledge(page: Page, publicationStatus: 'success' | 'failed' | 'running' = 'success') {
  let document = {
    id: 'policy', title: '巡检知识', content: '原有巡检建议', knowledge_type: 'risk_advice', category: 'risk_advice',
    region: null, province: null, city: null, task_types: [], risk_tags: [], warning_types: [], warning_levels: [],
    decision_scopes: [], keywords: [], visibility: 'public', tenant_id: 'public', user_id: null,
    version: 'v1', review_status: 'approved', is_active: true, index_dirty: false, effective_at: null, expires_at: null,
    source: 'manual', source_url: null, metadata: {}, created_at: '2026-11-26T00:00:00Z', updated_at: '2026-11-26T00:00:00Z',
  }
  let control = {
    paused: false, message: '知识库维护中', updated_by: null as string | null, updated_at: null,
    published_version: 'old-version', withdrawn_count: 0,
  }
  const jobs: Record<string, unknown>[] = []
  const writes: Array<{ path: string; body: unknown }> = []
  const unexpected: string[] = []
  let releasePublication!: (route: Route) => void
  const pendingPublication = new Promise<Route>((resolve) => { releasePublication = resolve })
  await page.addInitScript(() => localStorage.setItem('drone_agent_access_token', 'isolated-browser-test'))
  await page.route('**/test-api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/test-api', '')
    const method = request.method()
    if (method !== 'GET') writes.push({ path, body: request.postData() ? request.postDataJSON() : null })
    if (path === '/auth/me') return route.fulfill({ json: { id: 'admin', username: 'admin', role: 'admin', is_active: true } })
    if (path === '/admin/knowledge' && method === 'GET') return route.fulfill({ json: { items: [document], total: 1, page: 1, page_size: 10 } })
    if (path === '/admin/knowledge/index-jobs') return route.fulfill({ json: { items: jobs, total: jobs.length, page: 1, page_size: 5 } })
    if (path === '/admin/knowledge/retrieval-control') {
      if (method === 'PUT') control = { ...control, ...request.postDataJSON(), updated_by: 'admin' }
      return route.fulfill({ json: control })
    }
    if (path === '/admin/knowledge/policy' && method === 'PATCH') {
      document = { ...document, ...request.postDataJSON(), index_dirty: true }
      return route.fulfill({ json: document })
    }
    if (path === '/admin/knowledge/policy/status') {
      document = { ...document, ...request.postDataJSON(), index_dirty: true }
      control = { ...control, withdrawn_count: document.is_active ? 0 : 1 }
      return route.fulfill({ json: document })
    }
    if (path === '/admin/knowledge/reindex') {
      releasePublication(route)
      return
    }
    unexpected.push(`${method} ${path}`)
    return route.abort()
  })
  await page.goto('/admin/knowledge')
  await expect(page.getByRole('button', { name: '暂停全部检索', exact: true })).toBeEnabled()
  return {
    writes, unexpected, control: () => control, pendingPublication,
    async finishPublication() {
      const route = await pendingPublication
      const job = {
        id: 'publish-job', status: publicationStatus, index_type: 'hybrid', document_count: 1, chunk_count: 1,
        triggered_by_user_id: 'admin', started_at: '2026-11-26T00:00:00Z', finished_at: '2026-11-26T00:01:00Z',
        created_at: '2026-11-26T00:00:00Z', updated_at: '2026-11-26T00:01:00Z',
        error_message: publicationStatus === 'failed' ? '模拟构建失败' : null,
      }
      jobs.unshift(job)
      if (publicationStatus === 'success' || publicationStatus === 'running') {
        control = { ...control, published_version: 'new-version' }
        document = { ...document, index_dirty: publicationStatus === 'running' }
      }
      await route.fulfill({ json: job })
    },
  }
}

test('saving ordinary edits leaves them pending until publication completes', async ({ page }, testInfo) => {
  const api = await openKnowledge(page)
  await page.getByRole('button', { name: '编辑', exact: true }).click()
  await page.getByRole('textbox', { name: '内容', exact: true }).fill('补充后的巡检建议')
  await page.getByRole('button', { name: '保存知识', exact: true }).click()
  await expect(page.locator('.success-panel')).toContainText('待发布')
  await expect(page.locator('.dirty-index')).toHaveText('待发布')
  expect(api.control().published_version).toBe('old-version')
  expect(api.writes.map((write) => write.path)).toEqual(['/admin/knowledge/policy'])
  await page.getByRole('button', { name: '发布知识更新', exact: true }).click()
  await expect(page.getByRole('button', { name: '发布中...', exact: true })).toBeDisabled()
  await api.finishPublication()
  await expect(page.locator('.success-panel')).toContainText('新版已发布')
  await expect(page.locator('.clean-index')).toHaveText('已发布')
  expect(api.unexpected).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('knowledge-publication.png'), fullPage: true })
})

test('withdrawing one item does not pause all retrieval or publish a new index', async ({ page }) => {
  const api = await openKnowledge(page)
  await page.getByRole('button', { name: '立即撤回', exact: true }).click()
  await expect(page.locator('.success-panel')).toContainText('该知识已立即撤回')
  await expect(page.getByRole('button', { name: '启用（待发布）', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '暂停全部检索', exact: true })).toBeEnabled()
  expect(api.control().withdrawn_count).toBe(1)
  expect(api.control().published_version).toBe('old-version')
  expect(api.writes.map((write) => write.path)).toEqual(['/admin/knowledge/policy/status'])
  expect(api.unexpected).toEqual([])
})

test('a switched publication awaiting recovery is not reported as a failed switch', async ({ page }) => {
  const api = await openKnowledge(page, 'running')
  await page.getByRole('button', { name: '发布知识更新', exact: true }).click()
  await api.finishPublication()
  await expect(page.locator('.success-panel')).toContainText('发布状态正在自动恢复')
  await expect(page.locator('.error-panel')).toHaveCount(0)
  expect(api.control().published_version).toBe('new-version')
  expect(api.unexpected).toEqual([])
})

for (const status of ['success', 'failed'] as const) {
  test(`global pause requires manual recovery after a ${status} publication`, async ({ page }) => {
    const api = await openKnowledge(page, status)
    await page.getByRole('button', { name: '暂停全部检索', exact: true }).click()
    await expect(page.getByRole('button', { name: '恢复全部检索', exact: true })).toBeEnabled()
    await page.getByRole('button', { name: '发布知识更新', exact: true }).click()
    await api.finishPublication()
    if (status === 'failed') {
      await expect(page.locator('.error-panel')).toContainText('发布失败，当前已发布版本继续使用')
      await expect(page.locator('.success-panel')).toHaveCount(0)
    } else {
      await expect(page.locator('.success-panel')).toContainText('新版已发布')
    }
    await expect(page.getByRole('button', { name: '恢复全部检索', exact: true })).toBeEnabled()
    expect(api.control().paused).toBe(true)
    await page.getByRole('button', { name: '恢复全部检索', exact: true }).click()
    await expect(page.getByRole('button', { name: '暂停全部检索', exact: true })).toBeEnabled()
    expect(api.writes.filter((write) => write.path.endsWith('/retrieval-control'))).toHaveLength(2)
    expect(api.unexpected).toEqual([])
  })
}
