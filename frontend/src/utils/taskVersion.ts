export function taskResultVersion(value: unknown): number | null {
  if (!value || typeof value !== 'object') return null
  const data = value as { version?: unknown; request?: { task_version?: unknown } }
  const version = data.version ?? data.request?.task_version
  return typeof version === 'number' && Number.isInteger(version) && version > 0 ? version : null
}

export function canApplyTaskResult(result: unknown, task: { version: number | null; status: string }) {
  return task.status !== 'cancelled' && taskResultVersion(result) !== null && taskResultVersion(result) === task.version
}
