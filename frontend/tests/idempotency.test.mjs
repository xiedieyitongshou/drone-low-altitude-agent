import assert from 'node:assert/strict'
import { beforeEach, test } from 'node:test'
import { beginSubmission, completeSubmission, latestPendingSubmission } from '../src/utils/idempotency.ts'

beforeEach(() => {
  const storage = new Map()
  globalThis.window = { sessionStorage: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  } }
})

test('lost response and page restoration retain the operation ID and frozen payload', () => {
  const scope = crypto.randomUUID()
  const payload = { title: 'inspection', metadata: { a: 1, b: 2 } }
  const first = beginSubmission(scope, 'owner', payload)
  payload.title = 'edited locally'
  const restored = latestPendingSubmission(scope, 'owner')
  assert.equal(restored.key, first.key)
  assert.equal(restored.payload.title, 'inspection')
  assert.equal(beginSubmission(scope, 'owner', { title: 'inspection', metadata: { b: 2, a: 1 } }).key, first.key)
})

test('a confirmed submission permits another intentional identical creation', () => {
  const scope = crypto.randomUUID()
  const first = beginSubmission(scope, 'owner', { title: 'inspection' })
  completeSubmission(scope, 'owner', first.key)
  assert.equal(latestPendingSubmission(scope, 'owner'), undefined)
  assert.notEqual(beginSubmission(scope, 'owner', first.payload).key, first.key)
})

test('different users and operations do not share keys', () => {
  const scope = crypto.randomUUID()
  const first = beginSubmission(scope, 'owner', { title: 'inspection' })
  assert.notEqual(beginSubmission(scope, 'other', first.payload).key, first.key)
  assert.notEqual(beginSubmission(`${scope}.agent`, 'owner', first.payload).key, first.key)
})

test('editing and reverting an unresolved request does not lose the old retry ID', () => {
  const scope = crypto.randomUUID()
  const first = beginSubmission(scope, 'owner', { title: 'one' })
  const second = beginSubmission(scope, 'owner', { title: 'two' })
  assert.notEqual(first.key, second.key)
  assert.equal(beginSubmission(scope, 'owner', first.payload).key, first.key)
  completeSubmission(scope, 'owner', second.key)
  assert.equal(latestPendingSubmission(scope, 'owner').key, first.key)
})
