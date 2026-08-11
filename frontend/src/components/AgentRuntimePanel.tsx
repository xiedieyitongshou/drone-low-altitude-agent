import { JsonDetails } from './JsonDetails'
import type { AgentQueryResponse, AgentRuntimeDebug } from '../types/agent'
import {
  formatRuntimeErrors,
  hasContextMergeSignal,
  shouldOpenRuntime,
} from '../utils/agentRuntime'

type AgentRuntimePanelProps = {
  response: AgentQueryResponse
}

export function AgentRuntimePanel({ response }: AgentRuntimePanelProps) {
  const runtime = response.agent_runtime

  if (!runtime) {
    return (
      <div className="runtime-empty-panel">
        当前响应未返回 Agent Runtime 调试信息，页面已按旧响应格式兼容展示。
      </div>
    )
  }

  const errors = formatRuntimeErrors(runtime)

  return (
    <details className="runtime-panel" open={shouldOpenRuntime(response)}>
      <summary>
        <span>Agent Runtime</span>
        <strong>{runtime.status ?? 'unknown'}</strong>
      </summary>

      <div className="runtime-grid">
        <div>
          <span>mode</span>
          <strong>{runtime.mode ?? '-'}</strong>
        </div>
        <div>
          <span>trace_id</span>
          <strong>{runtime.trace_id ?? '-'}</strong>
        </div>
        <div>
          <span>run_id</span>
          <strong>{runtime.run_id ?? '-'}</strong>
        </div>
        <div>
          <span>fallback_used</span>
          <strong>{String(Boolean(runtime.fallback_used))}</strong>
        </div>
      </div>

      <RuntimeList title="计划动作 plan_actions" items={runtime.plan_actions} emptyText="暂无计划动作" />
      <RuntimeList title="工具结果 tool_results" items={runtime.tool_results} emptyText="暂无工具结果" />

      {errors.length > 0 ? (
        <div className="runtime-error-list">
          <strong>运行错误</strong>
          <ul>
            {errors.map((error, index) => (
              <li key={`${error}-${index}`}>{error}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <ContextMergePanel runtime={runtime} />
    </details>
  )
}

export function ContextMergePanel({ runtime }: { runtime: AgentRuntimeDebug }) {
  const merge = runtime.context_merge

  if (!merge) {
    return null
  }

  return (
    <details className="context-merge-panel" open={hasContextMergeSignal(runtime)}>
      <summary>
        <span>Context Merge</span>
        <strong>{hasContextMergeSignal(runtime) ? '存在上下文合并信息' : '无上下文变更'}</strong>
      </summary>

      <RuntimeList
        title="覆盖字段 modified_fields"
        items={merge.modified_fields}
        emptyText="本轮未覆盖历史字段"
      />
      <RuntimeList
        title="失效工具 invalidated_tools"
        items={merge.invalidated_tools}
        emptyText="本轮未标记工具结果失效"
      />

      <JsonDetails title="字段来源 field_sources" data={merge.field_sources ?? {}} />
    </details>
  )
}

function RuntimeList({
  title,
  items,
  emptyText,
}: {
  title: string
  items?: string[]
  emptyText: string
}) {
  return (
    <div className="runtime-list">
      <strong>{title}</strong>
      {items?.length ? (
        <div className="runtime-chip-row">
          {items.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      ) : (
        <p>{emptyText}</p>
      )}
    </div>
  )
}
