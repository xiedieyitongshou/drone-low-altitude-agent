import { expect, test } from '@playwright/test'
import type { Page, Route } from '@playwright/test'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

const evaluation = (version: number) => ({
  request: { location: '深圳', task_version: version },
  advice: { allow_cruise: true, overall_decision: '适合飞行', summary_risk_factors: [], hourly_assessment: [] },
})

// HTTP fixtures control response order; database races are covered by the
// PostgreSQL versioning gate. These tests exercise the real page and API client.
async function openTask(page: Page, holdEvaluationList = false) {
  let task = {
    id: 'race-task', version: 5, user_id: 'race-owner', title: '取消竞争测试任务',
    status: 'draft', location: '深圳', date: '2026-11-25',
    start_time: '14:00', end_time: '15:00', task_type: 'inspection',
    candidate_locations: [], selected_window: null, latest_decision: null as string | null,
    latest_request_id: null, latest_trace_id: null, latest_conversation_id: null,
    created_at: '2026-11-24T00:00:00Z', updated_at: '2026-11-24T00:00:00Z',
    profile_context: {}, metadata: {}, conversation_ids: [], request_ids: [], trace_ids: [],
  }
  const pendingEvaluation = deferred<Route>()
  const pendingList = deferred<{ route: Route; snapshot: typeof task }>()
  const writes: Array<{ method: string; path: string; body: unknown }> = []
  const unexpected: string[] = []
  let detailReads = 0

  await page.addInitScript(() => localStorage.setItem('drone_agent_access_token', 'isolated-browser-test'))
  await page.route('**/test-api/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/test-api', '')
    const method = request.method()
    if (method !== 'GET') writes.push({ method, path, body: request.postDataJSON() })
    if (path === '/auth/me' && method === 'GET') {
      return route.fulfill({ json: { id: 'race-owner', username: 'race-owner', display_name: null, role: 'user', is_active: true } })
    }
    if (path === '/tasks' && method === 'GET') {
      if (holdEvaluationList && task.status === 'evaluated') {
        holdEvaluationList = false
        pendingList.resolve({ route, snapshot: structuredClone(task) })
        return
      }
      return route.fulfill({ json: { items: [task], total: 1, page: 1, page_size: 10 } })
    }
    if (path === '/tasks/race-task' && method === 'GET') {
      detailReads++
      return route.fulfill({ json: task })
    }
    if (path === '/tasks/race-task/evaluate' && method === 'POST') {
      pendingEvaluation.resolve(route)
      return // The test releases this response after cancellation has finished.
    }
    if (path === '/tasks/race-task/status' && method === 'PATCH') {
      expect(request.postDataJSON()).toEqual({ status: 'cancelled', expected_version: task.version })
      task = { ...task, status: 'cancelled', version: task.version + 1 }
      return route.fulfill({ json: task })
    }
    unexpected.push(`${method} ${path}`)
    return route.abort()
  })

  await page.goto('/tasks')
  await page.getByRole('button', { name: /取消竞争测试任务/ }).click()
  await expect(page.getByRole('button', { name: '评估', exact: true })).toBeEnabled()
  return {
    pendingEvaluation, pendingList, writes, unexpected,
    detailReads: () => detailReads,
    applyEvaluation: () => { task = { ...task, version: 6, status: 'evaluated', latest_decision: '适合飞行' } },
  }
}

test('an older list response cannot replace the list refreshed after cancellation', async ({ page }) => {
  const api = await openTask(page, true)
  await page.getByRole('button', { name: '评估', exact: true }).click()
  const pending = await api.pendingEvaluation.promise
  api.applyEvaluation()
  await pending.fulfill({ json: evaluation(6) })
  const staleList = await api.pendingList.promise
  await expect(page.locator('.mission-hero-card strong').first()).toHaveText('已评估')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByText('已取消任务', { exact: true })).toBeVisible()
  await expect(page.locator('.mission-item.active .mission-status')).toHaveText('已取消')
  await staleList.route.fulfill({ json: { items: [staleList.snapshot], total: 1, page: 1, page_size: 10 } })
  // The evaluation action finishes only after its older list request settles.
  await expect(page.getByRole('button', { name: '评估中...', exact: true })).toHaveCount(0)
  await expect(page.locator('.mission-hero-card strong').first()).toHaveText('已取消')
  await expect(page.locator('.mission-item.active .mission-status')).toHaveText('已取消')
  expect(api.writes[1].body).toEqual({ status: 'cancelled', expected_version: 6 })
  expect(api.writes).toHaveLength(2)
  expect(api.unexpected).toEqual([])
})

async function cancelDuringEvaluation(page: Page) {
  const api = await openTask(page)
  await page.getByRole('button', { name: '评估', exact: true }).click()
  const pending = await api.pendingEvaluation.promise
  await expect(page.getByRole('button', { name: '评估中...', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: '取消', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByText('已取消任务', { exact: true })).toBeVisible()
  await expect(page.locator('.mission-item.active .mission-status')).toHaveText('已取消')
  return { api, pending }
}

async function expectCancelled(page: Page) {
  await expect(page.locator('.mission-hero-card strong').first()).toHaveText('已取消')
  await expect(page.locator('.mission-item.active .mission-status')).toHaveText('已取消')
  for (const name of ['评估', '推荐窗口', '执行前复核', '取消']) {
    await expect(page.getByRole('button', { name, exact: true })).toBeDisabled()
  }
  await expect(page.getByRole('button', { name: '评估中...', exact: true })).toHaveCount(0)
  await expect(page.getByText('已完成评估', { exact: true })).toHaveCount(0)
  await expect(page.locator('details').filter({ has: page.getByText('最近操作结果 JSON', { exact: true }) }).locator('pre')).toHaveText('暂无数据')
}

test('a normal evaluation still displays its current result', async ({ page }) => {
  const api = await openTask(page)
  await page.getByRole('button', { name: '评估', exact: true }).click()
  const pending = await api.pendingEvaluation.promise
  api.applyEvaluation()
  await pending.fulfill({ json: evaluation(6) })
  await expect(page.getByText('已完成评估', { exact: true })).toBeVisible()
  await expect(page.locator('.mission-hero-card strong').first()).toHaveText('已评估')
  await expect(page.locator('.mission-item.active .mission-status')).toHaveText('已评估')
  await expect(page.getByRole('button', { name: '评估', exact: true })).toBeEnabled()
  await expect(page.locator('details').last().locator('pre')).toContainText('"task_version": 6')
  expect(api.unexpected).toEqual([])
})

test('a delayed version conflict refreshes the page without undoing cancellation or retrying', async ({ page }) => {
  const { api, pending } = await cancelDuringEvaluation(page)
  const readsBeforeConflict = api.detailReads()
  await pending.fulfill({ status: 409, json: { error_code: 'TASK_VERSION_CONFLICT', message: '任务已发生变更，请刷新后重新操作。' } })
  await expect(page.getByText('任务已发生变更，请刷新后重新操作。', { exact: true })).toBeVisible()
  await expectCancelled(page)
  expect(api.detailReads()).toBeGreaterThan(readsBeforeConflict)
  expect(api.writes).toEqual([
    { method: 'POST', path: '/tasks/race-task/evaluate', body: { expected_version: 5 } },
    { method: 'PATCH', path: '/tasks/race-task/status', body: { status: 'cancelled', expected_version: 5 } },
  ])
  expect(api.unexpected).toEqual([])
})

for (const replyVersion of [5, 6]) {
  test(`a delayed success at version ${replyVersion} cannot become the current result of a cancelled task`, async ({ page }) => {
    const { api, pending } = await cancelDuringEvaluation(page)
    // Defensive transport fixture: cancellation winning on the real backend
    // normally produces 409; even a stale 200 must not revive a cancelled task.
    await pending.fulfill({ json: evaluation(replyVersion) })
    await expect(page.getByText('任务已有后续变更，已显示最新状态。', { exact: true })).toBeVisible()
    await expectCancelled(page)
    expect(api.writes).toHaveLength(2)
    expect(api.unexpected).toEqual([])
  })
}
