# Agent Eval 与 RAG Eval 数据集

## 目标

`evals/` 用于保存可版本管理的质量评估样例。它和 `tests/` 的职责不同：

- `tests/` 验证代码是否按预期运行。
- `evals/` 验证 Agent 决策质量和 RAG 召回质量是否符合业务期望。

Day106 只建立数据集结构和首批样例，后续 Day107-Day110 会基于这些样例实现评测脚本、指标统计和报告生成。

## 目录结构

```text
evals/
  agent/
    cases.json
  rag/
    cases.json
  README.md
```

## Agent Eval 样例字段

`evals/agent/cases.json` 用于评估 Agent 是否识别对意图、选择对工具、少调用工具、不越权、不编造结果。

核心字段：

- `id`：样例唯一标识。
- `category`：评测类别，例如 `evaluate`、`recommend`、`compare`、`query`、`clarification`、`modify`、`permission`、`tool_failure`。
- `input`：用户自然语言输入。
- `history_state`：可选历史状态，用于多轮修改、规则解释、权限和工具失败场景。
- `expected_intent`：期望意图。
- `expected_route`：期望业务路由或兜底路径。
- `expected_tools`：期望调用的工具。
- `unexpected_tools`：不应调用的工具。
- `expected_result_keywords`：期望最终输出包含的要点。
- `expected_fallback`：是否期望进入兜底。
- `notes`：样例设计目的。

## RAG Eval 样例字段

`evals/rag/cases.json` 用于评估知识检索是否命中期望知识、是否遵守 metadata filter、是否正确处理低置信和空召回。

核心字段：

- `id`：样例唯一标识。
- `category`：评测类别，例如 `policy_hint`、`sop`、`faq`、`permission`、`hybrid_rerank`、`fallback`。
- `query`：检索问题。
- `business_context`：任务类型、风险标签、地区等业务上下文。
- `access_context`：用户、租户、角色等访问上下文。
- `expected_knowledge_ids`：期望命中的知识 ID。
- `expected_excluded_knowledge_ids`：期望不能被召回的知识 ID。
- `expected_knowledge_types`：期望命中的知识类型。
- `expected_chunk_types`：期望命中的 chunk 类型。
- `expected_metadata`：期望 metadata 条件。
- `expected_behavior`：空召回、二次召回、fallback 等行为期望。
- `top_k`：评估召回前 K 个结果。
- `notes`：样例设计目的。

## 覆盖范围

当前 Agent Eval 覆盖：

- 单地点风险评估。
- 飞行窗口推荐。
- 多地点比选。
- 历史查询。
- 规则解释。
- 缺字段追问。
- 多轮修改。
- 用户越权。
- 工具失败兜底。

当前 RAG Eval 覆盖：

- 政策提示 `policy_hint`。
- SOP 步骤检索。
- FAQ 问答对检索。
- 私有知识权限隔离。
- Hybrid metadata boost 与规则 rerank。
- 空召回 query rewrite。
- 低置信 fallback。

## 后续指标

后续脚本应基于这些样例输出：

- 意图识别准确率。
- 工具选择准确率。
- 不应调用工具违规率。
- 缺字段追问通过率。
- 多轮状态修改通过率。
- 权限拦截通过率。
- 工具失败恢复通过率。
- RAG Recall@K。
- RAG metadata filter 通过率。
- RAG fallback 通过率。

## 设计原则

- 数据集要小而精，优先覆盖项目最关键路径。
- 样例必须能解释为什么存在，避免堆无意义 case。
- 期望结果以结构化字段为主，文本关键词只做辅助判断。
- Eval 不替代单元测试，而是补充 Agent 和 RAG 的质量度量。
