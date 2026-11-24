import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canApplyTaskResult, taskResultVersion } from '../src/utils/taskVersion.ts'

test('a delayed assessment cannot replace a later cancellation or edit', () => {
  const result = { request: { task_version: 2 } }
  assert.equal(canApplyTaskResult(result, { version: 3, status: 'cancelled' }), false)
  assert.equal(canApplyTaskResult(result, { version: 3, status: 'draft' }), false)
  assert.equal(canApplyTaskResult(result, { version: 2, status: 'evaluated' }), true)
})

test('unversioned historical snapshots cannot be used as a current result', () => {
  assert.equal(taskResultVersion({ id: 'old', version: null }), null)
  assert.equal(canApplyTaskResult({ request: {} }, { version: 1, status: 'draft' }), false)
  assert.equal(taskResultVersion({ id: 'new', version: 4 }), 4)
})
