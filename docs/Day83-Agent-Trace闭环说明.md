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

1. `AgentLoop` 初始化一次运行，生成 `trace_id`、`run_id`
2. `AgentLoop` 进入计划、工具调用、兜底、最终输出等阶段
3. `ToolExecutor` 负责执行工具，并自动记录 `tool_call`、`tool_result`、`error`
4. `record_trace_event` / `record_trace_events` 将事件写入数据库
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

事件字段：

- `event_type`：事件类型，如 `plan`、`tool_call`、`tool_result`、`error`、`fallback`
- `status_before` / `status_after`：状态转换前后
- `tool_name`：调用的工具名
- `latency_ms`：工具耗时
- `input_summary` / `output_summary`：脱敏后的输入输出摘要
- `error_code`：错误类型
- `metadata`：错误分类、恢复动作、兜底来源等扩展信息

## 隐私边界

trace 用于排查问题，但不能无边界记录原始数据。

当前策略：

- token、password、authorization、api_key、phone 等敏感字段会被替换为 `[REDACTED]`
- 长文本会被截断，避免日志和 trace 中保存过多原始输入
- trace 查询按 `user_id` 过滤，不提供跨用户查询入口

这对面试项目是有价值的，因为它说明项目不是只实现功能，还考虑了企业 Agent 系统里的审计、隔离和最小化暴露。

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

## 面试表达

可以这样描述 Day78-Day83 的改造：

> 我没有只停留在 workflow 返回最终结果，而是给 Agent 增加了 trace 体系。每次运行都会记录状态转换、工具调用、错误分类和兜底路径，并且 trace 可以按用户权限查询。这样一方面支持线上问题排查，另一方面也能解释 Agent 的工作过程，避免黑盒化。

这部分能体现的能力：

- Agent loop 工程化
- tool calling 可观测性
- 错误分类与恢复策略
- 用户级数据隔离
- trace 与日志的职责拆分
- 面向企业系统的审计意识
