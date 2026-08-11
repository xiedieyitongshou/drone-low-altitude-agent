# Day73：Agent State 结构与状态转换说明

## 目标

Day73 说明当前 AgentState 的结构、字段含义和状态转换路径。

当前 AgentState 表达的是一次 Agent run 的执行状态，不是后续任务单中的业务状态。

## AgentState 核心字段

当前 AgentState 的核心字段：

```text
query
user_id
session_id
trace_id
run_id
status
current_intent
task_draft
confirmed_fields
missing_fields
tool_results
errors
steps
round_index
```

字段含义：

| 字段 | 含义 |
| --- | --- |
| `query` | 原始用户输入 |
| `user_id` | 当前用户 |
| `session_id` | 当前会话 |
| `trace_id` | 一次 Agent 执行链路 ID |
| `run_id` | 一次运行 ID |
| `status` | 当前 Agent 执行态 |
| `current_intent` | 当前业务意图，例如 `evaluate`、`recommend`、`compare` |
| `task_draft` | 解析结果、上下文和用户补充信息合并后的任务草稿 |
| `confirmed_fields` | 已确认字段 |
| `missing_fields` | 当前还缺少的字段 |
| `tool_results` | 已执行工具的结果 |
| `errors` | 工具失败、权限拒绝或运行时错误 |
| `steps` | 状态变化记录，用于 trace 和调试 |
| `round_index` | 当前步骤序号 |

## Agent 执行态

当前 AgentState 的状态枚举：

```text
initialized
parsed
needs_clarification
ready_to_plan
tool_running
tool_completed
failed
completed
```

状态含义：

| 状态 | 含义 |
| --- | --- |
| `initialized` | AgentState 已创建，尚未完成解析 |
| `parsed` | 解析事件已记录 |
| `needs_clarification` | 缺少必要字段，需要追问用户 |
| `ready_to_plan` | 字段基本完整，可以进入 Planner |
| `tool_running` | 工具正在执行 |
| `tool_completed` | 工具执行成功，已有工具结果 |
| `failed` | 工具失败、权限失败、Guardrail 拒绝或状态异常 |
| `completed` | 本次 Agent run 完成 |

## 状态转换路径

状态转换路径不是 LLM 自由生成的，而是由 Rule Planner、AgentLoop 和状态更新函数确定性推进。

### 成功路径

```text
initialized
  -> ready_to_plan
  -> tool_running
  -> tool_completed
  -> completed
```

含义：

- 初始化 AgentState。
- 解析出完整 intent 和字段。
- Planner 选择工具。
- AgentLoop 标记工具运行。
- ToolExecutor 执行成功。
- AgentLoop 记录工具结果并完成响应。

### 缺字段路径

```text
initialized
  -> needs_clarification
```

含义：

- 用户输入不完整。
- 解析器或 Planner 判断缺少 required fields。
- AgentLoop 返回追问，而不是强行调用工具。

### 工具失败路径

```text
initialized
  -> ready_to_plan
  -> tool_running
  -> failed
  -> fallback
```

含义：

- Planner 正常选择工具。
- 工具执行失败，例如天气服务超时、工具异常、空结果。
- AgentState 记录 error。
- AgentLoop 进入 fallback 或直接返回可解释失败结果。

### Guardrail 拒绝路径

```text
initialized
  -> ready_to_plan
  -> tool_running
  -> failed
  -> deny 或 fallback
```

含义：

- Planner 可以生成工具调用。
- 但 Tool Guardrail 在工具执行前发现认证、权限、角色或风险边界不满足。
- AgentLoop 不执行真实工具 handler。
- 最终返回拒绝、追问或降级结果。

## steps 的作用

`steps` 不是业务数据，而是一次 Agent run 内部的状态变化记录。

它用于：

- 解释 Agent 为什么进入某个状态。
- 记录状态变化前后的关键 delta。
- 支撑 trace 展示。
- 支撑 Agent Eval 和失败排查。

典型 step event：

```text
initialize
parse
needs_clarification
tool_running
tool_result
complete
fail
```

## 和 MissionTask.status 的区别

当前 `AgentState.status` 描述一次 Agent run 的执行过程：

```text
initialized / ready_to_plan / tool_running / completed
```

后续任务单中的业务状态描述一个低空作业任务生命周期：

```text
draft / evaluated / scheduled / recheck / completed / cancelled
```

两者职责不同：

```text
AgentState.status
负责一次对话或一次 Agent run 怎么执行

MissionTask.status
负责一个低空作业任务从草稿到复核完成怎么流转
```

两者可以通过以下字段关联：

```text
task_id
trace_id
conversation_id
request_id
```

但不应该混成同一个状态机。

## 设计价值

AgentState 的价值不是把流程复杂化，而是让 Agent Runtime 具备以下能力：

- 缺字段时能追问，而不是失败或编造。
- 多轮补充字段后能继续规划。
- 用户修改字段后能重算受影响工具。
- 工具失败后能记录错误并选择 fallback。
- Trace 能解释一次 Agent run 的完整执行路径。

