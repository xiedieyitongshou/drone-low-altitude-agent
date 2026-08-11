# Day72：Rule Planner 运行逻辑说明

## 目标

Day72 说明当前 Agent Runtime 中 Planner 的定位和运行逻辑。

当前系统中确实存在 Planner，但它是规则型 Planner，不是 LLM Planner。它的目标不是让大模型自由规划工具调用，而是基于显式状态、业务路由和工具注册表做确定性决策。

## 当前定位

当前设计更准确地说是：

```text
规则 Planner 驱动的可控 Agent Runtime
```

而不是：

```text
LLM Planner Agent
```

当前分工：

- LLM 或规则解析器负责把自然语言解析成 `intent` 和结构化字段。
- Business Route 负责把 `intent` 映射到目标接口、必填字段和主工具。
- Rule Planner 根据 `AgentState.status`、`current_intent`、`missing_fields`、业务路由和工具注册表决定下一步动作。
- AgentLoop 执行 Planner 结果，并调用状态更新函数推进 AgentState。
- Guardrail 固定在输入、工具调用和最终输出阶段执行，不由 Planner 自由选择是否调用。

## Planner 动作集合

当前 Rule Planner 的动作集合是固定的：

```text
ask_clarification
call_tool
respond_directly
fallback
```

含义：

| 动作 | 含义 |
| --- | --- |
| `ask_clarification` | 缺少必要字段，需要追问用户 |
| `call_tool` | 当前状态已经满足调用工具条件 |
| `respond_directly` | 已有工具结果或状态已完成，可以生成最终响应 |
| `fallback` | 状态异常、意图不支持、工具不存在或失败，需要降级 |

## 核心判断顺序

Rule Planner 的核心判断顺序：

```text
如果 AgentState.status == completed
  -> respond_directly

如果 AgentState.status == failed
  -> fallback

如果 AgentState.status == tool_running
  -> fallback

如果 AgentState.status == tool_completed
  -> respond_directly

如果缺少 required_fields
  -> ask_clarification

如果 intent 为空或不支持
  -> fallback

如果 intent 支持
  -> 根据 Business Route 找到 primary_tool
  -> call_tool
```

这说明当前 Planner 的行为是可预测的，不依赖 LLM 临场生成执行计划。

## Intent 到工具的映射

意图到工具的映射由业务路由控制：

```text
evaluate  -> evaluate_flight_risk
recommend -> recommend_flight_windows
compare   -> compare_flight_locations
knowledge -> query_knowledge_snippets
explain   -> explain_risk_rules
history   -> query_user_history
```

这种设计的价值是：新增业务能力时优先新增 Business Route 和 Tool，而不是继续在 `/agent/query` 中堆复杂 if/else。

## 和固定 Workflow 的区别

固定 Workflow 通常是：

```text
解析输入
  -> 固定调用评估
  -> 固定调用推荐
  -> 固定调用 RAG
  -> 返回结果
```

当前 Rule Planner Runtime 是：

```text
解析输入
  -> 生成 AgentState
  -> Planner 判断下一步
  -> AgentLoop 执行动作
  -> 更新 AgentState
  -> Planner 再判断下一步
```

区别在于当前链路不会无条件跑完整流程，而是根据 `intent`、缺失字段、工具结果和失败状态决定下一步动作。

## 为什么当前不用 LLM Planner

低空作业气象决策属于高风险业务，工具选择、缺参追问、权限边界和失败恢复必须可测试、可回归、可解释。

如果直接让 LLM 规划工具调用，会带来几个问题：

- 可能选择不存在或不合适的工具。
- 可能跳过必要字段检查。
- 可能绕过权限、租户或用户隔离。
- 工具失败后的恢复路径难以稳定复现。
- Eval 和回归测试成本明显上升。

因此当前第一版采用 Rule Planner，更适合展示 Agent 工程可控性。

## 后续 LLM Planner 升级方式

后续如果要引入 LLM Planner，不建议直接替换当前 Planner，而是采用混合规划：

```text
LLM Planner 生成候选 plan
Rule Planner / Plan Validator 校验候选 plan
Guardrail 检查工具权限、风险等级、参数完整性和越权行为
校验通过后 AgentLoop 执行
校验失败时回退到 Rule Planner
```

推荐边界：

- LLM 可以提出候选工具调用计划。
- Tool Registry 限制 LLM 只能选择已注册工具。
- Rule Planner 或 Plan Validator 校验字段完整性、工具存在性和业务约束。
- Guardrail 校验权限、租户、用户隔离、高风险输出和越权行为。
- LLM Planner 失败、不合法或不确定时，回退到当前 Rule Planner。

这样可以保留 LLM 的灵活性，同时不牺牲安全链路的确定性。

