import { useEffect, useMemo, useState } from 'react'
import {
  createAdminKnowledge,
  deleteAdminKnowledge,
  listAdminKnowledge,
  listAdminKnowledgeIndexJobs,
  reindexAdminKnowledge,
  updateAdminKnowledge,
  updateAdminKnowledgeStatus,
} from '../api/admin'
import type {
  KnowledgeCategory,
  KnowledgeDocument,
  KnowledgeDocumentPayload,
  KnowledgeIndexJob,
  KnowledgeReviewStatus,
  KnowledgeType,
  KnowledgeVisibility,
} from '../types/admin'

type FormState = {
  id?: string
  title: string
  content: string
  knowledge_type: KnowledgeType
  category: KnowledgeCategory | ''
  region: string
  province: string
  city: string
  task_types: string
  risk_tags: string
  warning_types: string
  warning_levels: string
  decision_scopes: string
  keywords: string
  visibility: KnowledgeVisibility
  tenant_id: string
  user_id: string
  version: string
  review_status: KnowledgeReviewStatus
  is_active: boolean
  effective_at: string
  expires_at: string
  source: string
  source_url: string
  metadata: string
}

const emptyForm: FormState = {
  title: '',
  content: '',
  knowledge_type: 'risk_advice',
  category: 'risk_advice',
  region: '',
  province: '',
  city: '',
  task_types: '',
  risk_tags: '',
  warning_types: '',
  warning_levels: '',
  decision_scopes: '',
  keywords: '',
  visibility: 'public',
  tenant_id: 'public',
  user_id: '',
  version: 'v1',
  review_status: 'draft',
  is_active: true,
  effective_at: '',
  expires_at: '',
  source: '',
  source_url: '',
  metadata: '{}',
}

export function AdminKnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [jobs, setJobs] = useState<KnowledgeIndexJob[]>([])
  const [form, setForm] = useState<FormState>(emptyForm)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [knowledgeType, setKnowledgeType] = useState<KnowledgeType | ''>('')
  const [reviewStatus, setReviewStatus] = useState<KnowledgeReviewStatus | ''>('')
  const [isActive, setIsActive] = useState<boolean | ''>('')
  const [visibility, setVisibility] = useState<KnowledgeVisibility | ''>('')
  const [city, setCity] = useState('')
  const [indexDirty, setIndexDirty] = useState<boolean | ''>('')
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isReindexing, setIsReindexing] = useState(false)

  useEffect(() => {
    void loadDocuments()
    void loadJobs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  const latestJob = jobs[0]
  const totalPages = useMemo(() => Math.max(Math.ceil(total / 10), 1), [total])

  async function loadDocuments(nextPage = page) {
    setIsLoading(true)
    setErrorMessage('')
    try {
      const response = await listAdminKnowledge({
        page: nextPage,
        page_size: 10,
        keyword: keyword.trim() || undefined,
        knowledge_type: knowledgeType,
        review_status: reviewStatus,
        is_active: isActive,
        visibility,
        city: city.trim() || undefined,
        index_dirty: indexDirty,
      })
      setDocuments(response.items)
      setTotal(response.total)
      setPage(response.page)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '加载知识列表失败')
    } finally {
      setIsLoading(false)
    }
  }

  async function loadJobs() {
    try {
      const response = await listAdminKnowledgeIndexJobs(1, 5)
      setJobs(response.items)
    } catch {
      setJobs([])
    }
  }

  async function handleSave() {
    setIsSaving(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const payload = buildPayload(form)
      const saved = form.id
        ? await updateAdminKnowledge(form.id, payload)
        : await createAdminKnowledge(payload)
      setForm(toFormState(saved))
      setSuccessMessage(form.id ? '知识已更新，索引状态已标记为待重建。' : '知识已新增。')
      await loadDocuments(1)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '保存知识失败')
    } finally {
      setIsSaving(false)
    }
  }

  async function handleStatusChange(
    document: KnowledgeDocument,
    payload: { review_status?: KnowledgeReviewStatus; is_active?: boolean },
  ) {
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const updated = await updateAdminKnowledgeStatus(document.id, {
        ...payload,
        index_dirty: true,
      })
      setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      if (form.id === updated.id) {
        setForm(toFormState(updated))
      }
      setSuccessMessage('知识状态已更新，索引状态已标记为待重建。')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '更新知识状态失败')
    }
  }

  async function handleDelete(document: KnowledgeDocument) {
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const updated = await deleteAdminKnowledge(document.id)
      setDocuments((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      if (form.id === updated.id) {
        setForm(toFormState(updated))
      }
      setSuccessMessage('知识已禁用，保留记录用于审计。')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '禁用知识失败')
    }
  }

  async function handleReindex() {
    setIsReindexing(true)
    setErrorMessage('')
    setSuccessMessage('')
    try {
      const job = await reindexAdminKnowledge()
      setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)].slice(0, 5))
      setSuccessMessage(`索引重建完成：${job.document_count} 条知识，${job.chunk_count} 个切片。`)
      await loadDocuments()
      await loadJobs()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '重建索引失败')
    } finally {
      setIsReindexing(false)
    }
  }

  return (
    <section className="page-card admin-page admin-knowledge-page">
      <div className="page-header">
        <div>
          <h2>RAG 知识库管理</h2>
          <p>维护数据库知识、审核发布，并触发 BM25 / Embedding / TF-IDF 索引重建。</p>
        </div>
        <button type="button" onClick={() => void handleReindex()} disabled={isReindexing}>
          {isReindexing ? '重建中...' : '重建索引'}
        </button>
      </div>

      <div className="admin-index-status">
        <div>
          <span>最近索引任务</span>
          <strong>{latestJob ? latestJob.status : '暂无任务'}</strong>
          <small>
            {latestJob
              ? `${latestJob.index_type} / docs ${latestJob.document_count} / chunks ${latestJob.chunk_count}`
              : '创建或审核知识后可手动重建索引'}
          </small>
        </div>
        <div>
          <span>待重建知识</span>
          <strong>{documents.filter((item) => item.index_dirty).length}</strong>
          <small>当前页 index_dirty=true 的数量</small>
        </div>
      </div>

      <form
        className="agent-form admin-filter-form"
        onSubmit={(event) => {
          event.preventDefault()
          void loadDocuments(1)
        }}
      >
        <label>
          <span>关键词</span>
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} />
        </label>
        <label>
          <span>知识类型</span>
          <select value={knowledgeType} onChange={(event) => setKnowledgeType(event.target.value as KnowledgeType | '')}>
            <option value="">全部</option>
            <option value="risk_advice">risk_advice</option>
            <option value="sop">sop</option>
            <option value="policy_hint">policy_hint</option>
            <option value="faq">faq</option>
          </select>
        </label>
        <label>
          <span>审核状态</span>
          <select value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value as KnowledgeReviewStatus | '')}>
            <option value="">全部</option>
            <option value="draft">draft</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
            <option value="expired">expired</option>
          </select>
        </label>
        <label>
          <span>启用状态</span>
          <select value={isActive === '' ? '' : String(isActive)} onChange={(event) => setIsActive(toBooleanFilter(event.target.value))}>
            <option value="">全部</option>
            <option value="true">启用</option>
            <option value="false">禁用</option>
          </select>
        </label>
        <label>
          <span>可见性</span>
          <select value={visibility} onChange={(event) => setVisibility(event.target.value as KnowledgeVisibility | '')}>
            <option value="">全部</option>
            <option value="public">public</option>
            <option value="tenant">tenant</option>
            <option value="private">private</option>
          </select>
        </label>
        <label>
          <span>城市</span>
          <input value={city} onChange={(event) => setCity(event.target.value)} />
        </label>
        <label>
          <span>索引状态</span>
          <select value={indexDirty === '' ? '' : String(indexDirty)} onChange={(event) => setIndexDirty(toBooleanFilter(event.target.value))}>
            <option value="">全部</option>
            <option value="true">待重建</option>
            <option value="false">已同步</option>
          </select>
        </label>
        <div className="form-actions">
          <button type="submit" disabled={isLoading}>
            {isLoading ? '查询中...' : '查询知识'}
          </button>
        </div>
      </form>

      {errorMessage ? <div className="error-panel">{errorMessage}</div> : null}
      {successMessage ? <div className="success-panel">{successMessage}</div> : null}

      <div className="admin-knowledge-layout">
        <div className="admin-table-wrapper">
          <table className="admin-table admin-knowledge-table">
            <thead>
              <tr>
                <th>标题</th>
                <th>状态</th>
                <th>范围</th>
                <th>有效期</th>
                <th>来源</th>
                <th>索引</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => (
                <tr key={document.id}>
                  <td>
                    <strong>{document.title}</strong>
                    <small>{document.knowledge_type} / {document.version}</small>
                  </td>
                  <td>
                    <StatusBadge value={document.review_status} />
                    <span>{document.is_active ? '启用' : '禁用'}</span>
                  </td>
                  <td>
                    <span>{document.visibility}</span>
                    <small>{[document.province, document.city].filter(Boolean).join(' / ') || document.tenant_id}</small>
                  </td>
                  <td>
                    <small>{document.effective_at || '未设置开始'}</small>
                    <small>{document.expires_at || '未设置过期'}</small>
                  </td>
                  <td>
                    <span>{document.source || '-'}</span>
                    <small>{document.source_url || '-'}</small>
                  </td>
                  <td>
                    <span className={document.index_dirty ? 'dirty-index' : 'clean-index'}>
                      {document.index_dirty ? '待重建' : '已同步'}
                    </span>
                  </td>
                  <td>
                    <div className="admin-action-row">
                      <button type="button" className="secondary-button" onClick={() => setForm(toFormState(document))}>
                        编辑
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void handleStatusChange(document, { is_active: !document.is_active })}
                      >
                        {document.is_active ? '禁用' : '启用'}
                      </button>
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => void handleStatusChange(document, { review_status: 'approved' })}
                      >
                        审核通过
                      </button>
                      <button type="button" className="secondary-button" onClick={() => void handleDelete(document)}>
                        软删除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!documents.length ? (
                <tr>
                  <td colSpan={7}>暂无知识记录。</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <KnowledgeEditor
          form={form}
          isSaving={isSaving}
          onChange={setForm}
          onReset={() => setForm(emptyForm)}
          onSave={() => void handleSave()}
        />
      </div>

      <div className="pagination-row">
        <button
          type="button"
          className="secondary-button"
          disabled={page <= 1 || isLoading}
          onClick={() => setPage((current) => Math.max(current - 1, 1))}
        >
          上一页
        </button>
        <span>
          共 {total} 条 / {page} / {totalPages}
        </span>
        <button
          type="button"
          className="secondary-button"
          disabled={page >= totalPages || isLoading}
          onClick={() => setPage((current) => current + 1)}
        >
          下一页
        </button>
      </div>

      <section className="result-section">
        <h3>最近索引任务</h3>
        <div className="admin-table-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>任务 ID</th>
                <th>状态</th>
                <th>索引类型</th>
                <th>文档/切片</th>
                <th>触发人</th>
                <th>完成时间</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id}>
                  <td>{job.id}</td>
                  <td><StatusBadge value={job.status} /></td>
                  <td>{job.index_type}</td>
                  <td>{job.document_count} / {job.chunk_count}</td>
                  <td>{job.triggered_by_user_id || '-'}</td>
                  <td>{job.finished_at || job.updated_at}</td>
                </tr>
              ))}
              {!jobs.length ? (
                <tr>
                  <td colSpan={6}>暂无索引任务。</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}

function KnowledgeEditor({
  form,
  isSaving,
  onChange,
  onReset,
  onSave,
}: {
  form: FormState
  isSaving: boolean
  onChange: (next: FormState) => void
  onReset: () => void
  onSave: () => void
}) {
  return (
    <form
      className="knowledge-editor"
      onSubmit={(event) => {
        event.preventDefault()
        onSave()
      }}
    >
      <div className="knowledge-editor-header">
        <h3>{form.id ? '编辑知识' : '新增知识'}</h3>
        <button type="button" className="secondary-button" onClick={onReset}>
          清空
        </button>
      </div>
      <label>
        <span>标题</span>
        <input value={form.title} onChange={(event) => onChange({ ...form, title: event.target.value })} required />
      </label>
      <label>
        <span>内容</span>
        <textarea value={form.content} onChange={(event) => onChange({ ...form, content: event.target.value })} required />
      </label>
      <div className="knowledge-editor-grid">
        <label>
          <span>知识类型</span>
          <select value={form.knowledge_type} onChange={(event) => onChange({ ...form, knowledge_type: event.target.value as KnowledgeType })}>
            <option value="risk_advice">risk_advice</option>
            <option value="sop">sop</option>
            <option value="policy_hint">policy_hint</option>
            <option value="faq">faq</option>
          </select>
        </label>
        <label>
          <span>分类</span>
          <select value={form.category} onChange={(event) => onChange({ ...form, category: event.target.value as KnowledgeCategory | '' })}>
            <option value="">未设置</option>
            <option value="risk_advice">risk_advice</option>
            <option value="warning_advice">warning_advice</option>
            <option value="task_advice">task_advice</option>
            <option value="execution_advice">execution_advice</option>
          </select>
        </label>
        <label>
          <span>审核状态</span>
          <select value={form.review_status} onChange={(event) => onChange({ ...form, review_status: event.target.value as KnowledgeReviewStatus })}>
            <option value="draft">draft</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
            <option value="expired">expired</option>
          </select>
        </label>
        <label>
          <span>可见性</span>
          <select value={form.visibility} onChange={(event) => onChange({ ...form, visibility: event.target.value as KnowledgeVisibility })}>
            <option value="public">public</option>
            <option value="tenant">tenant</option>
            <option value="private">private</option>
          </select>
        </label>
      </div>
      <div className="knowledge-editor-grid">
        <TextInput label="区域" value={form.region} onChange={(value) => onChange({ ...form, region: value })} />
        <TextInput label="省份" value={form.province} onChange={(value) => onChange({ ...form, province: value })} />
        <TextInput label="城市" value={form.city} onChange={(value) => onChange({ ...form, city: value })} />
        <TextInput label="租户" value={form.tenant_id} onChange={(value) => onChange({ ...form, tenant_id: value })} />
      </div>
      <div className="knowledge-editor-grid">
        <TextInput label="任务类型" value={form.task_types} onChange={(value) => onChange({ ...form, task_types: value })} />
        <TextInput label="risk_tags" value={form.risk_tags} onChange={(value) => onChange({ ...form, risk_tags: value })} />
        <TextInput label="warning_types" value={form.warning_types} onChange={(value) => onChange({ ...form, warning_types: value })} />
        <TextInput label="keywords" value={form.keywords} onChange={(value) => onChange({ ...form, keywords: value })} />
      </div>
      <div className="knowledge-editor-grid">
        <TextInput label="warning_levels" value={form.warning_levels} onChange={(value) => onChange({ ...form, warning_levels: value })} />
        <TextInput label="decision_scopes" value={form.decision_scopes} onChange={(value) => onChange({ ...form, decision_scopes: value })} />
        <TextInput label="版本" value={form.version} onChange={(value) => onChange({ ...form, version: value })} />
        <TextInput label="所属用户" value={form.user_id} onChange={(value) => onChange({ ...form, user_id: value })} />
      </div>
      <div className="knowledge-editor-grid">
        <TextInput label="生效时间" value={form.effective_at} onChange={(value) => onChange({ ...form, effective_at: value })} />
        <TextInput label="过期时间" value={form.expires_at} onChange={(value) => onChange({ ...form, expires_at: value })} />
        <TextInput label="来源" value={form.source} onChange={(value) => onChange({ ...form, source: value })} />
        <TextInput label="来源 URL" value={form.source_url} onChange={(value) => onChange({ ...form, source_url: value })} />
      </div>
      <label>
        <span>metadata JSON</span>
        <textarea value={form.metadata} onChange={(event) => onChange({ ...form, metadata: event.target.value })} />
      </label>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(event) => onChange({ ...form, is_active: event.target.checked })}
        />
        <span>启用知识</span>
      </label>
      <div className="form-actions">
        <button type="submit" disabled={isSaving}>
          {isSaving ? '保存中...' : '保存知识'}
        </button>
      </div>
    </form>
  )
}

function TextInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      <span>{label}</span>
      <input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  )
}

function StatusBadge({ value }: { value: string }) {
  return <span className={`knowledge-status-badge knowledge-status-${value}`}>{value}</span>
}

function toBooleanFilter(value: string): boolean | '' {
  return value === '' ? '' : value === 'true'
}

function toFormState(document: KnowledgeDocument): FormState {
  return {
    id: document.id,
    title: document.title,
    content: document.content,
    knowledge_type: document.knowledge_type,
    category: document.category ?? '',
    region: document.region ?? '',
    province: document.province ?? '',
    city: document.city ?? '',
    task_types: document.task_types.join(', '),
    risk_tags: document.risk_tags.join(', '),
    warning_types: document.warning_types.join(', '),
    warning_levels: document.warning_levels.join(', '),
    decision_scopes: document.decision_scopes.join(', '),
    keywords: document.keywords.join(', '),
    visibility: document.visibility,
    tenant_id: document.tenant_id,
    user_id: document.user_id ?? '',
    version: document.version,
    review_status: document.review_status,
    is_active: document.is_active,
    effective_at: document.effective_at ?? '',
    expires_at: document.expires_at ?? '',
    source: document.source ?? '',
    source_url: document.source_url ?? '',
    metadata: JSON.stringify(document.metadata ?? {}, null, 2),
  }
}

function buildPayload(form: FormState): KnowledgeDocumentPayload {
  return {
    title: form.title.trim(),
    content: form.content.trim(),
    knowledge_type: form.knowledge_type,
    category: form.category || null,
    region: nullableText(form.region),
    province: nullableText(form.province),
    city: nullableText(form.city),
    task_types: splitCsv(form.task_types),
    risk_tags: splitCsv(form.risk_tags),
    warning_types: splitCsv(form.warning_types),
    warning_levels: splitCsv(form.warning_levels),
    decision_scopes: splitCsv(form.decision_scopes),
    keywords: splitCsv(form.keywords),
    visibility: form.visibility,
    tenant_id: form.tenant_id.trim() || 'public',
    user_id: nullableText(form.user_id),
    version: form.version.trim() || 'v1',
    review_status: form.review_status,
    is_active: form.is_active,
    index_dirty: true,
    effective_at: nullableText(form.effective_at),
    expires_at: nullableText(form.expires_at),
    source: nullableText(form.source),
    source_url: nullableText(form.source_url),
    metadata: JSON.parse(form.metadata || '{}') as KnowledgeDocumentPayload['metadata'],
  }
}

function splitCsv(value: string) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function nullableText(value: string) {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}
