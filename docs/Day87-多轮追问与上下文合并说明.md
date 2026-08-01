# Day87：多轮追问与上下文合并说明

## 目标

Day87 的目标是在 Agent Runtime 下支持多轮追问、pending task 保存和上下文合并。

这里不直接把 Redis 或 TTLCache 写进 Agent，而是复用已有 `session_memory_store` 抽象。Agent 只关心“加载会话上下文、保存待补全任务、合并上下文”，不关心底层是 `ttlcache`、`redis` 还是 `database`。

## 字段补齐优先级

当前 Agent loop 模式下的字段来源优先级：

```text
用户本轮显式输入
  > Session Memory / pending task
  > Profile
  > 系统默认值
  > 追问用户
```

不同任务的策略不同：

- 评估、推荐、比选属于安全决策类任务，不用 Profile 默认地点直接补齐安全关键字段。
- 查询类任务可以使用 Profile 默认地点、默认任务类型等信息提升体验。
- `task_type` 可以从 Profile 补齐，因为它是任务规则模板，不是具体飞行地点或时间。
- `scan_hours`、`top_k`、分页参数等低风险字段可以使用系统默认值。

## 安全边界

安全关键字段包括：

- `location`
- `locations`
- `date`
- `start_time`
- `end_time`

这些字段直接影响风险评估结论。如果没有来自用户本轮输入或 session pending task 的明确上下文，Agent 会追问，而不是直接使用 Profile 默认值。

例如：

```text
用户：明天下午能飞吗？
系统：还需要补充任务地点。
```

即使用户 Profile 里有默认地点，Agent loop 也不会直接拿默认地点去做风险评估。

## Pending Task 链路

当用户输入缺字段时：

1. Parser 返回可识别的部分结构化字段
2. AgentContextManager 生成 pending task
3. `session_memory_store` 保存 pending task
4. AgentLoop 返回追问
5. 下一轮用户补充字段后，AgentContextManager 合并 pending task 和本轮输入
6. AgentLoop 继续执行工具

示例：

```text
第一轮：明天下午能飞吗？
  -> 保存 date/start_time/end_time/task_type
  -> 追问 location

第二轮：深圳
  -> 合并上一轮 date/start_time/end_time
  -> 使用本轮 location=深圳
  -> 继续执行 evaluate_flight_risk
```

## 与 Profile 的兼容

Profile 仍然保留原有能力：

- legacy workflow 继续沿用原来的 `merge_profile_context`
- Agent loop 下查询类任务可以使用 Profile 默认地点和任务类型
- Agent loop 下安全决策类任务只使用 Profile 的 `task_type`

这样既兼容之前的 Profile 设计，又避免 Agent 在安全评估场景下过度自动补全关键字段。

## 面试表达

可以这样描述：

> 我没有让 Agent 随意猜测缺失参数，而是做了字段来源分层。用户本轮输入优先，其次是 session pending task，再是 Profile 和系统默认值。安全决策类任务缺地点、日期、时间会追问；查询类任务可以使用 Profile 提升体验。底层会话存储继续复用现有 `session_memory_store`，所以本地可以用 TTLCache，部署时可以切 Redis 或数据库。
