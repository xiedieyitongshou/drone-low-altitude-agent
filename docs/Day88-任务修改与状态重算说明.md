# Day88：任务修改与状态重算说明

## 目标

Day88 的目标是支持用户在多轮对话中修改任务条件，并让 Agent 基于新输入重新计算状态，再从新状态继续规划工具。

这里不是针对某个固定字段做特殊逻辑，而是把“修改”视为一次新的用户输入覆盖：

```text
上一轮 session context / pending task
  ↓
用户本轮显式修改字段
  ↓
user_input 覆盖 session/profile/default
  ↓
重新计算 AgentState
  ↓
重新 resolve missing_fields
  ↓
重新 plan_next_step
```

## 修改识别

当前支持的典型表达包括：

- `地点改成广州`
- `改成深圳`
- `时间改成后天下午`
- `任务类型改成测绘`
- `还是下午，但地点换成珠海`

这些表达不会创建一个独立的 `modify` 工具，而是复用上一轮的业务意图。例如上一轮是 `evaluate`，用户说“地点改成广州”后，仍然按 `evaluate` 重新规划。

## 字段覆盖策略

字段来源优先级延续 Day87：

```text
user_input > session/pending_task > profile > default
```

Day88 新增了两个调试字段：

- `modified_fields`：本轮用户显式覆盖了哪些旧字段
- `invalidated_tools`：这些字段变化会让哪些工具结果失效

例如：

```json
{
  "modified_fields": ["location"],
  "invalidated_tools": ["evaluate_flight_risk", "query_knowledge_snippets"]
}
```

## 受影响工具判断

当前判断逻辑保持轻量：

- 修改 `location`、`locations`、`date`、`start_time`、`end_time`、`task_type` 时，当前业务主工具结果失效。
- 修改 `location`、`city`、`province`、`region`、`task_type`、`risk_reasons`、`overall_decision` 时，知识查询结果失效。

这意味着：

- 修改飞行区域后，应重新计算风险评估。
- 修改飞行区域后，后续如果需要 RAG，也应重新检索知识片段。
- 当前阶段只记录受影响工具并重走主工具路径；RAG 是否作为可选工具调用放到 Day89。

## 与旧 workflow 的区别

旧 workflow 更像每次从头执行：

```text
输入 -> 解析 -> 固定链路 -> 输出
```

Day88 的 Agent loop 更像状态重算：

```text
旧状态 + 用户修改
  -> 新 AgentState
  -> 判断缺字段
  -> 调用受影响工具
  -> 输出新结果
```

这能说明 Agent State 的价值：不需要把所有流程写死，而是让用户修改成为状态转换的一部分。
