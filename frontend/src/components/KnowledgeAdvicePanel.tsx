import type { JsonValue } from '../types/agent'

type KnowledgeAdvicePanelProps = {
  details?: Record<string, unknown> | Record<string, JsonValue> | null
}

type AdviceItem = {
  id?: string
  title?: string
  advice_text?: string
  priority?: string
  action_type?: string
  source?: string
  matched_by?: string[]
}

type KnowledgeSnippet = {
  id?: string
  title?: string
  content?: string
  score?: number
  source?: string
  source_url?: string
}

export function KnowledgeAdvicePanel({ details }: KnowledgeAdvicePanelProps) {
  const advice = normalizeList<AdviceItem>(details?.advice)
  const snippets = normalizeList<KnowledgeSnippet>(details?.knowledge_snippets)

  if (advice.length === 0 && snippets.length === 0) {
    return null
  }

  return (
    <section className="result-section knowledge-panel">
      <h3>知识库建议 / RAG 检索片段</h3>

      {advice.length > 0 ? (
        <div className="knowledge-block">
          <span>操作建议</span>
          <div className="knowledge-list">
            {advice.map((item, index) => (
              <article className="knowledge-card" key={item.id ?? index}>
                <strong>{item.title ?? '建议条目'}</strong>
                <p>{item.advice_text ?? '暂无建议内容'}</p>
                <div className="response-badges">
                  {item.priority ? <span>priority: {item.priority}</span> : null}
                  {item.action_type ? <span>action: {item.action_type}</span> : null}
                  {item.source ? <span>source: {item.source}</span> : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}

      {snippets.length > 0 ? (
        <div className="knowledge-block">
          <span>检索片段</span>
          <div className="knowledge-list">
            {snippets.map((item, index) => (
              <article className="knowledge-card snippet-card" key={item.id ?? index}>
                <strong>{item.title ?? '知识片段'}</strong>
                <p>{item.content ?? '暂无片段内容'}</p>
                <div className="response-badges">
                  {typeof item.score === 'number' ? (
                    <span>score: {item.score.toFixed(3)}</span>
                  ) : null}
                  {item.source ? <span>source: {item.source}</span> : null}
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function normalizeList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}
