# Day83：Agent Trace 查询闭环说明

## 目标

Day83 的目标不是继续增加新的业务能力，而是把第十三周已经完成的 trace、日志、错误兜底能力串成一个可查询、可解释、可溯源的闭环。

核心结果：

- Agent 每次运行都会生成 `trace_id` 和 `run_id`
- 工具调用、状态变化、异常、兜底、最终输出都会写入 `agent_trace_events`
- 用户可以通过接口查询自己本次 Agent 运行的完整 trace
- trace 查询严格按当前登录用户过滤，避免用户之间互相查看执行过程

## Trace 数据链路

当前 trace 链路如下：

1. `/agent/query` 在读取上下文和解析前生成本次请求的 `trace_id`、`run_id`，主路径及 legacy 兜底共用这两个 ID
2. 解析、计划、追问、工具调用、Guardrail、兜底和最终响应写入同一条 Trace
3. `ToolExecutor` 负责执行工具，并自动记录 `tool_call`、`tool_result`、`error`
4. 请求内收集事件，结束时通过 `record_trace_events` 一次提交；Trace 保存失败会提示降级，不重跑业务工具
5. `GET /agent/traces/{trace_id}` 按用户查询 trace 明细

这条链路解决的是“Agent 为什么给出这个结果”的问题，而不是只看最终返回值。

## 查询接口

### `GET /agent/traces/{trace_id}`

用途：

- 查看某次 Agent 运行的完整执行过程
- 定位工具调用是否成功
- 查看状态是否按预期转换
- 查看错误类型、兜底策略和最终输出路径

权限：

- 必须登录
- 只能查询当前用户自己的 trace
- 查询不存在或不属于当前用户的 trace 时返回 `404`

返回结构：

- `trace_id`：一次 Agent 执行链路的追踪 ID
- `run_id`：一次 Agent loop 运行 ID
- `event_count`：事件数量
- `events`：按 `step_index` 和数据库 ID 排序后的事件列表
- `request_ids`、`conversation_ids`、`task_ids`：本次执行关联的评估快照、对话与任务单
- `outcome`：`success`、`clarification`、`failed` 或 `degraded`
- `timings`：本次处理及各阶段计时

事件字段：

- `event_type`：事件类型，如 `parse`、`plan`、`clarification`、`tool_call`、`tool_result`、`error`、`fallback`、`stage`、`final_response`
- `status_before` / `status_after`：状态转换前后
- `tool_name`：调用的工具名
- `latency_ms`：工具耗时
- `input_summary` / `output_summary`：脱敏后的输入输出摘要
- `error_code`：错误类型
- `metadata`：错误分类、恢复动作、兜底来源等扩展信息

## 业务结果关联

普通 Loop 评估会复用天气及规则计算结果，保存请求、天气快照、规则快照和最终结论，并组装 `composed` 输出。
`/agent/query` 返回的 `request_id`、`conversation_id`、`trace_id` 可分别用于查询历史、对话和执行过程。
对话列表也返回 `request_id` 和 `trace_id`；历史评估返回 `trace_id`。新保存的普通评估按用户归属校验，其他用户不能通过请求 ID 读回。

历史快照写入失败时，保留已计算的规则结论，`request.persistence_status` 为 `failed` 且不返回不存在的 `request_id`。
知识建议或解释失败时可回退为规则结果模板；对话或 Trace 保存失败同样不重跑天气请求和已完成的工具。

本次新增数据库版本 `c6a2f41d8e90`，运行前执行 `python -m alembic upgrade head`。
旧记录的关联字段保持空值，不根据历史日志猜测关联关系；原有无归属公开评估的读取行为保持兼容。

## 分段计时

计时使用单调时钟，按请求隔离，复用现有工具计时。`timings.stages` 按实际执行情况包含：

- `context_read`、`context_merge`、`parser`、`planner`
- `tool`、`weather`、`weather_http`、`rules`
- `history_write`、`session_write`、`profile_write`、`knowledge`、`composition`、`llm`

每项记录 `calls`、`failures`、`duration_ms` 和 `self_ms`。
`failures` 统计该阶段抛出异常的次数；工具返回业务失败、追问和降级分别以工具结果及 `outcome` 判断，不能只用异常次数代表业务成功率。
`duration_ms` 包含嵌套阶段，不能将所有阶段直接相加；`self_ms` 扣除已计时的直接子阶段。
例如解析包含一次 LLM 调用时，解析总耗时包含 LLM 耗时，解析自身耗时会扣除该调用。
`weather` 包含客户端重试和退避，`weather_http` 单独计量每次实际 HTTP 尝试，失败尝试也会计数。
未执行的阶段不生成虚假的零耗时样本。

`processing_ms` 从 Agent 入口计时，到业务处理和结果组装结束为止，不包含最后的对话、Trace 提交以及 HTTP 序列化和网络传输。
因此它用于定位后端处理阶段，不替代从客户端测得的端到端延迟。
这些数据先通过现有后端接口返回，当前没有新增展示页面或跨用户查询权限。

请求正常退出后才提交缓冲事件；进程被强制终止前未提交的 Trace 不保证保留。

## 验收方式

在现有 pytest 内覆盖普通评估关联、追问及续接、天气超时、附属保存失败、跨用户权限和并发计时隔离。
天气使用固定的 HTTP 回放，LLM 分段计时使用模拟 HTTP 响应；这些用例验证记录正确性，不用于声称真实供应商的响应性能。

## 隐私边界

trace 用于排查问题，但不能无边界记录原始数据。

当前策略：

- token、password、authorization、api_key、phone 等敏感字段会被替换为 `[REDACTED]`
- 长文本会被截断，避免日志和 trace 中保存过多原始输入
- trace 查询按 `user_id` 过滤，不提供跨用户查询入口

## 与日志的区别

日志主要用于运行时排查：

- 适合看系统什么时候报错
- 适合看服务整体运行状态
- 适合接入控制台或日志平台

trace 主要用于解释 Agent 决策链路：

- 适合看 Agent 经过了哪些状态
- 适合看调用了哪些工具
- 适合看为什么进入兜底
- 适合复盘某一次具体用户请求

两者互补。日志解决“系统层面发生了什么”，trace 解决“这次 Agent 是怎么做出结果的”。
