# Day86：查询类能力工具化说明

## 目标

Day86 的目标是支持“只查询、不评估、不推荐”的轻量路径，避免用户只是问历史、知识库或规则依据时，系统仍然触发完整风险评估链路。

## 本次工具化能力

| 工具 | 意图 | 作用 | 是否触发风险评估 |
| --- | --- | --- | --- |
| `query_user_history` | `history` | 查询当前用户历史会话和任务记录 | 否 |
| `query_knowledge_snippets` | `knowledge` | 查询知识库片段、政策提示、SOP、FAQ | 否 |
| `explain_risk_rules` | `explain` | 解释风险规则来源、任务阈值和预警修正逻辑 | 否 |

其中 `query_knowledge_snippets` 复用已有 RAG 检索能力，但在 Agent 路由层作为独立查询工具暴露，语义上和“评估后补建议”区分开。

## 规则解释边界

用户问“为什么判高风险”时，当前系统不会重新跑一次天气评估，而是调用 `explain_risk_rules` 返回：

- 任务类型对应的规则 profile
- 禁飞阈值和慎飞阈值
- 高风险预警如何修正结论
- 规则来源模块
- 如果上下文里有上一轮风险原因，则补充说明这些风险原因来自已识别评估结果

当前解释来源是项目内规则：

- `app.rules.mission_profiles`
- `app.rules.cruise`

这能说明“为什么这么判”，但不等同于实时政策审批或设备侧飞控限制结论。

## 不做无人机型号查询的原因

当前项目没有无人机型号库，也没有机型、载荷、续航、抗风等级、价格、适用任务等结构化数据。

因此 Day86 不实现“无人机型号查询工具”。如果后续接入设备库，再新增：

- `drone_models` 数据表
- `query_drone_models` 工具
- 机型 metadata
- 任务类型、载荷、续航、抗风能力筛选逻辑

这个边界比硬编码机型推荐更合理，也避免在面试中被追问数据来源时无法解释。

## 和 Day85 的关系

Day85 完成了业务路由配置。

Day86 在这个基础上补齐查询类工具：

```text
history   -> query_user_history
knowledge -> query_knowledge_snippets
explain   -> explain_risk_rules
```

这样 Agent 可以根据用户目标选择轻量查询路径，而不是默认执行完整 workflow。
