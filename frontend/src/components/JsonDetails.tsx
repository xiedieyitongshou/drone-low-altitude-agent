import type { JsonValue } from '../types/agent'

type JsonDetailsProps = {
  title: string
  data?: JsonValue | Record<string, JsonValue> | null
  defaultOpen?: boolean
}

export function JsonDetails({ title, data, defaultOpen = false }: JsonDetailsProps) {
  return (
    <details className="json-details" open={defaultOpen}>
      <summary>{title}</summary>
      <pre>{data ? JSON.stringify(data, null, 2) : '暂无数据'}</pre>
    </details>
  )
}
