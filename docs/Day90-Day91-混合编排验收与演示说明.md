# Day90-Day91：混合编排验收与演示说明

## 目标

Day90-Day91 主要做第 14 周收尾，不再新增大功能。

目标是验证同一个 `/agent/query` 自然语言入口下，Agent 能根据业务意图选择不同工具路径，而不是固定执行完整 workflow。

## 验收覆盖

已新增 `tests/test_agent_mixed_orchestration_e2e.py`，从 `/agent/query` 编排入口视角覆盖：

| 类型 | 示例输入 | 期望工具路径 |
| --- | --- | --- |
| 评估 | 深圳明天下午2点到5点适合做无人机巡检吗 | `evaluate_flight_risk` |
| 推荐 | 广州未来72小时什么时候最适合航测 | `recommend_flight_windows` |
| 比选 | 深圳、广州和珠海明天下午哪个更适合低空巡航 | `compare_flight_locations` |
| 历史查询 | 查一下我上次深圳任务记录 | `query_user_history` |
| 知识查询 | 深圳无人机巡检政策有什么要注意 | `query_knowledge_snippets` |
| 缺字段追问 | 明天下午能飞吗 | `ask_clarification` |
| 多轮修改 | 地点改成广州 | 重新规划 `evaluate_flight_risk` |

这组测试的重点不是调用真实天气 API，而是验证编排决策：

- 意图识别是否正确
- 工具路径是否正确
- 查询类是否跳过完整评估
- 缺字段是否追问并保存 pending task
- 修改类是否基于 session context 重算状态
- RAG 是否按策略调用或跳过

## 演示脚本

### 1. 查询类问题不触发评估

输入：

```text
查一下我上次深圳任务记录
```

预期：

- intent 为 `history`
- 工具为 `query_user_history`
- `rag_decision=skip_rag`
- 不调用风险评估工具

可讲点：

> 这个入口不是固定 workflow。用户只是查历史时，Agent 只调用历史查询工具，不会浪费成本去跑天气和规则评估。

### 2. 缺字段追问和多轮补齐

第一轮：

```text
明天下午能飞吗
```

预期：

- intent 为 `evaluate`
- 缺少 `location`
- 返回追问
- session 中保存 pending task

第二轮：

```text
深圳
```

预期：

- 使用上一轮 pending task 的日期和时间
- 本轮 `深圳` 补齐地点
- 继续调用 `evaluate_flight_risk`

可讲点：

> AgentState 不是每次从零开始，而是把 pending task 保存到 Session Memory。下一轮用户补充字段后，系统合并上下文再继续规划。

### 3. 多轮修改触发状态重算

已有上下文：

```text
深圳 明天下午 巡检
```

用户修改：

```text
地点改成广州
```

预期：

- `location` 从深圳变为广州
- `modified_fields=["location"]`
- `invalidated_tools=["evaluate_flight_risk", "query_knowledge_snippets"]`
- 重新规划风险评估工具

可讲点：

> 修改不是简单拼接文本，而是用户输入覆盖旧状态。状态变化后，Agent 重新判断缺字段和受影响工具，再向目标状态推进。

## Workflow 与 Agent 的区别

旧 workflow：

```text
自然语言 -> 解析 -> 固定执行评估/推荐/比选 -> 输出
```

第 14 周后的 Agent loop：

```text
自然语言
  -> 意图识别
  -> Business Route
  -> Context Manager 合并上下文
  -> Planner 选择工具
  -> ToolExecutor 执行
  -> Trace 记录路径
  -> 输出或追问
```

核心区别：

- 不同意图走不同工具路径
- 查询类任务可以跳过评估
- 缺字段可以保存 pending 并追问
- 修改类输入会触发状态重算
- RAG 是可选工具，不是固定链路
- trace 能解释每一步为什么发生
