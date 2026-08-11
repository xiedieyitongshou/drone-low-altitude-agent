# Day85：自然语言单入口业务路由设计

## 目标

Day85 的目标是把 `/agent/query` 从“固定业务链路入口”升级为“自然语言单入口 + 业务路由入口”。

用户只需要输入一句自然语言，系统先判断这句话属于哪类业务任务，再让 Agent Planner 基于业务路由选择对应工具。

## 当前支持的业务任务

| 意图 | 业务含义 | 主要工具 | 接口路径 |
| --- | --- | --- | --- |
| `evaluate` | 单地点飞行风险评估 | `evaluate_flight_risk` | `/cruise/evaluate` |
| `recommend` | 飞行窗口推荐 | `recommend_flight_windows` | `/cruise/recommend` |
| `compare` | 多地点比选 | `compare_flight_locations` | `/cruise/compare` |
| `knowledge` | 知识库、政策、SOP、FAQ 查询 | `retrieve_rag_advice` | `/knowledge/advice/retrieve` |
| `history` | 当前用户历史会话和任务查询 | `query_user_history` | `/agent/conversations` |

## 业务路由与 Agent Runtime 的关系

第十二周已经完成了 Agent 基础骨架：

- `Tool Registry`：统一管理可调用工具
- `AgentState`：保存任务状态
- `Rule Planner`：决定下一步动作
- `AgentLoop`：循环执行计划
- `ToolExecutor`：执行工具并记录 trace

Day85 做的是把这些工程能力和具体业务绑定起来：

```text
用户输入
  ↓
NL Parser 识别 intent / parsed
  ↓
Business Route 找到业务路径
  ↓
Planner 判断缺失字段和工具路径
  ↓
ToolExecutor 调用对应工具
  ↓
Trace 记录路由、工具、状态和结果
```

这里不是把完整流程重新写死，而是把“任务类型 → 必要字段 → 工具路径 → 兜底方式”配置化。后续增加新的业务任务时，优先新增业务路由和工具，而不是在 `/agent/query` 中堆 if/else。

## Rule Planner 与 Agent State 说明

当前 `/agent/query` 后面的 Agent Runtime 不是 LLM 自由规划，而是规则 Planner 驱动的可控运行时。

详细说明已拆到 Day72 和 Day73：

- [Day72：Rule Planner 运行逻辑说明](Day72-Rule-Planner运行逻辑说明.md)
- [Day73：Agent State 结构与状态转换说明](Day73-Agent-State结构与状态转换说明.md)

Day85 只保留业务路由入口视角：自然语言输入先识别 `intent`，再通过 Business Route 映射到必填字段和主工具，最后交给 Planner 与 AgentLoop 执行。
## 用户输入样例集

已新增 `data/agent_input_samples.json`，用于沉淀典型自然语言输入。

样例覆盖：

- 单地点评估
- 缺字段追问
- 飞行窗口推荐
- 多地点比选
- 历史查询
- 地区政策查询
- SOP 查询
- 多轮条件修改

这份样例集后续可以继续扩展为 Agent Eval 数据集，用于评估：

- 意图识别是否正确
- 工具路径是否正确
- 缺字段追问是否合理
- 多轮修改是否复用上下文
- RAG 查询是否召回到合理知识

## 当前实现边界

当前 Day85 只做轻量规则增强，不把所有意图判断都交给大模型：

- `evaluate`、`recommend`、`compare` 沿用已有规则能力
- `history` 通过“历史、上次、任务记录”等关键词识别
- `knowledge` 通过“政策、规则、SOP、知识库、注意事项”等关键词识别
- 多轮修改依赖已有 session context，例如“把地点改成佛山，时间还是明天下午”

后续如果要增强，可以把 `data/agent_input_samples.json` 作为评估集，再逐步引入 LLM intent classifier 或 reranker，而不是直接替换规则链路。

