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
  source_url?: string
  matched_by?: string[]
}

type KnowledgeSnippet = {
  id?: string
  knowledge_id?: string
  chunk_id?: string
  title?: string
  content?: string
  score?: number
  source?: string
  source_url?: string
  knowledge_type?: string
  chunk_type?: string
  retriever?: string
  retrievers?: string[]
  metadata_boost?: number
  rerank_boost?: number
  metadata?: Record<string, JsonValue>
}

type RetrievalMetadata = {
  retriever?: string
  retrievers?: string[]
  query_rewritten?: boolean
  rewrite_query?: string
  attempts?: Array<Record<string, JsonValue>>
  metadata_boost?: number
  rerank_boost?: number
  [key: string]: unknown
}

export function KnowledgeAdvicePanel({ details }: KnowledgeAdvicePanelProps) {
  const advice = normalizeList<AdviceItem>(details?.advice)
  const snippets = normalizeList<KnowledgeSnippet>(
    details?.knowledge_snippets ?? details?.snippets,
  )
  const retrievalStatus = readString(details?.retrieval_status)
  const retrievalMessage = readString(details?.retrieval_message)
  const retrievalMetadata = readObject<RetrievalMetadata>(details?.retrieval_metadata)
  const dataSource = getDataSource(details)

  if (
    advice.length === 0 &&
    snippets.length === 0 &&
    !retrievalStatus &&
    !retrievalMessage &&
    !retrievalMetadata
  ) {
    return null
  }

  return (
    <section className="result-section knowledge-panel">
      <div className="knowledge-panel-header">
        <div>
          <h3>知识库建议 / RAG 证据</h3>
          <p>RAG 只做解释增强和操作建议，不替代气象安全规则裁决。</p>
        </div>
        <div className="rag-header-badges">
          {dataSource ? <span className="rag-source-badge">{dataSource}</span> : null}
          {retrievalStatus ? (
            <span className={`rag-status-badge ${getRetrievalTone(retrievalStatus)}`}>
              {retrievalStatus}
            </span>
          ) : null}
        </div>
      </div>

      <ConservativeNotice
        retrievalStatus={retrievalStatus}
        retrievalMessage={retrievalMessage}
        adviceCount={advice.length}
        snippetCount={snippets.length}
      />

      {retrievalMetadata ? <RetrievalMetadataSummary metadata={retrievalMetadata} /> : null}

      <AdviceSection advice={advice} />
      <SnippetSection snippets={snippets} />

      {retrievalMetadata ? (
        <details className="rag-dev-details">
          <summary>检索元数据 retrieval_metadata</summary>
          <pre>{JSON.stringify(retrievalMetadata, null, 2)}</pre>
        </details>
      ) : (
        <div className="rag-empty-panel">暂无 retrieval_metadata，开发者排序依据仅展示片段字段。</div>
      )}
    </section>
  )
}

function ConservativeNotice({
  retrievalStatus,
  retrievalMessage,
  adviceCount,
  snippetCount,
}: {
  retrievalStatus: string
  retrievalMessage: string
  adviceCount: number
  snippetCount: number
}) {
  const shouldWarn =
    retrievalStatus === 'fallback' ||
    retrievalStatus.toLowerCase().includes('low_confidence') ||
    Boolean(retrievalMessage) ||
    (snippetCount === 0 && adviceCount > 0)

  if (!shouldWarn) {
    return null
  }

  return (
    <div className="rag-conservative-panel">
      <strong>保守提示</strong>
      <p>
        {retrievalMessage ||
          '当前 RAG 证据不足或置信度偏低，建议以规则引擎结论和现场安全流程为准。'}
      </p>
    </div>
  )
}

function AdviceSection({ advice }: { advice: AdviceItem[] }) {
  if (!advice.length) {
    return <div className="rag-empty-panel">暂无知识库操作建议。</div>
  }

  return (
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
              {item.source_url ? <span>source_url: {item.source_url}</span> : null}
              {item.matched_by?.length ? (
                <span>matched_by: {item.matched_by.join('、')}</span>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function SnippetSection({ snippets }: { snippets: KnowledgeSnippet[] }) {
  if (!snippets.length) {
    return (
      <div className="rag-empty-panel">
        暂无依据片段。若同时出现保守提示，应按规则引擎结论和现场流程处理。
      </div>
    )
  }

  return (
    <div className="knowledge-block">
      <span>依据片段</span>
      <div className="knowledge-list">
        {snippets.map((item, index) => (
          <article
            className="knowledge-card snippet-card"
            key={item.chunk_id ?? item.knowledge_id ?? item.id ?? index}
          >
            <strong>{item.title ?? '知识片段'}</strong>
            <p>{item.content ?? '暂无片段内容'}</p>
            <div className="response-badges">
              {typeof item.score === 'number' ? (
                <span>score: {item.score.toFixed(3)}</span>
              ) : null}
              {item.source ? <span>source: {item.source}</span> : null}
              {item.source_url ? <span>source_url: {item.source_url}</span> : null}
              {item.retriever ? <span>retriever: {item.retriever}</span> : null}
              {item.retrievers?.length ? (
                <span>retrievers: {item.retrievers.join('、')}</span>
              ) : null}
              {item.knowledge_type ? <span>knowledge_type: {item.knowledge_type}</span> : null}
              {item.chunk_type ? <span>chunk_type: {item.chunk_type}</span> : null}
            </div>

            <details className="rag-dev-details">
              <summary>开发者证据字段</summary>
              <div className="rag-dev-grid">
                <div>
                  <span>knowledge_id</span>
                  <strong>{item.knowledge_id ?? item.id ?? '-'}</strong>
                </div>
                <div>
                  <span>chunk_id</span>
                  <strong>{item.chunk_id ?? '-'}</strong>
                </div>
                <div>
                  <span>metadata_boost</span>
                  <strong>{formatOptionalNumber(item.metadata_boost)}</strong>
                </div>
                <div>
                  <span>rerank_boost</span>
                  <strong>{formatOptionalNumber(item.rerank_boost)}</strong>
                </div>
              </div>
              {item.metadata ? <pre>{JSON.stringify(item.metadata, null, 2)}</pre> : null}
            </details>
          </article>
        ))}
      </div>
    </div>
  )
}

function RetrievalMetadataSummary({ metadata }: { metadata: RetrievalMetadata }) {
  const retrievers = metadata.retrievers?.length
    ? metadata.retrievers.join('、')
    : metadata.retriever
  const latestAttempt = metadata.attempts?.[metadata.attempts.length - 1]

  return (
    <div className="rag-metadata-summary">
      {retrievers ? (
        <div>
          <span>retriever</span>
          <strong>{retrievers}</strong>
        </div>
      ) : null}
      <div>
        <span>query_rewritten</span>
        <strong>{String(Boolean(metadata.query_rewritten))}</strong>
      </div>
      {metadata.rewrite_query ? (
        <div>
          <span>rewrite_query</span>
          <strong>{metadata.rewrite_query}</strong>
        </div>
      ) : null}
      {metadata.attempts?.length ? (
        <div>
          <span>attempts</span>
          <strong>{metadata.attempts.length}</strong>
        </div>
      ) : null}
      {latestAttempt?.status ? (
        <div>
          <span>latest_status</span>
          <strong>{String(latestAttempt.status)}</strong>
        </div>
      ) : null}
      {latestAttempt?.top_score !== undefined ? (
        <div>
          <span>top_score</span>
          <strong>{formatJsonNumber(latestAttempt.top_score)}</strong>
        </div>
      ) : null}
    </div>
  )
}

function normalizeList<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function readString(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function readObject<T>(value: unknown): T | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as T) : null
}

function formatOptionalNumber(value?: number) {
  return typeof value === 'number' ? value.toFixed(3) : '-'
}

function formatJsonNumber(value: JsonValue) {
  return typeof value === 'number' ? value.toFixed(3) : String(value)
}

function getRetrievalTone(status: string) {
  if (status === 'fallback' || status.toLowerCase().includes('low_confidence')) {
    return 'warning'
  }

  if (status.includes('success')) {
    return 'success'
  }

  return 'neutral'
}

function getDataSource(details: KnowledgeAdvicePanelProps['details']) {
  if (!details) {
    return ''
  }
  if (details.knowledge_snippets) {
    return 'composed.details.knowledge_snippets'
  }
  if (details.snippets) {
    return 'composed.details.snippets'
  }
  if (details.advice) {
    return 'composed.details.advice'
  }
  return ''
}
