export type PendingSubmission<T> = { key: string; payload: T }

const fallback = new Map<string, PendingSubmission<unknown>[]>()

function storageKey(scope: string, userId: string) {
  return JSON.stringify(['drone.pending-submissions', scope, userId])
}

function read<T>(scope: string, userId: string): PendingSubmission<T>[] {
  const name = storageKey(scope, userId)
  try {
    const saved = window.sessionStorage.getItem(name)
    if (saved) {
      const parsed: unknown = JSON.parse(saved)
      if (Array.isArray(parsed) && parsed.every((item) => item && typeof item.key === 'string' && item.payload)) {
        return parsed
      }
    }
  } catch { /* Retain retry identity in memory if browser storage is unavailable. */ }
  return (fallback.get(name) ?? []) as PendingSubmission<T>[]
}

function write<T>(scope: string, userId: string, entries: PendingSubmission<T>[]) {
  const name = storageKey(scope, userId)
  fallback.set(name, entries)
  try {
    if (entries.length) window.sessionStorage.setItem(name, JSON.stringify(entries))
    else window.sessionStorage.removeItem(name)
  } catch { /* The in-memory copy still protects retries in this page. */ }
}

function signature(payload: unknown) {
  return JSON.stringify(payload, (_key, value) => (
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]]))
      : value
  ))
}

export function latestPendingSubmission<T>(scope: string, userId: string) {
  return read<T>(scope, userId).at(-1)
}

export function beginSubmission<T>(scope: string, userId: string, payload: T): PendingSubmission<T> {
  const entries = read<T>(scope, userId)
  const existing = entries.find((entry) => signature(entry.payload) === signature(payload))
  if (existing) return existing
  const submission = { key: crypto.randomUUID(), payload: JSON.parse(JSON.stringify(payload)) as T }
  write(scope, userId, [...entries, submission])
  return submission
}

export function completeSubmission(scope: string, userId: string, key: string) {
  write(scope, userId, read(scope, userId).filter((entry) => entry.key !== key))
}
