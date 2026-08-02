# Day89：RAG 作为可选工具接入说明

## 目标

Day89 的目标不是增强 RAG 检索算法，而是把 RAG 放到 Agent 编排策略里，明确什么时候调用、什么时候跳过。

当前 RAG 继续复用已有本地知识库和 Day67-Day70 的 metadata 数据治理能力。BM25、Embedding、Hybrid Retrieval、rerank、query rewrite 和 RAG Eval 放到第 17 周实现。

## 当前 RAG 工具

标准工具入口：

```text
query_knowledge_snippets
```

它复用已有知识库检索能力，继续支持：

- `task_type`
- `risk_reasons`
- `warning_types`
- `region`
- `province`
- `city`
- `top_k`
- `visibility`
- `tenant_id`
- `user_id`
- `review_status`
- `effective_at / expires_at`

也就是说，Day89 做的是编排层接入，不是重写检索层。

## 调用策略

会调用 RAG 的情况：

- 用户明确问政策
- 用户明确问 SOP
- 用户明确问 FAQ
- 用户明确问知识库内容
- 用户明确要操作建议、注意事项、风险说明

不会调用 RAG 的情况：

- 纯历史查询：走 `query_user_history`
- 缺字段追问：先补齐任务信息
- 纯参数修改：先重新计算 AgentState
- 风险评估：优先走规则引擎
- 窗口推荐：优先走推荐工具
- 多地点比选：优先走比选工具
- 规则来源解释：优先走 `explain_risk_rules`

## 策略记录

Planner 会在 metadata 中记录：

```json
{
  "rag_decision": "use_rag",
  "rag_reason": "knowledge intent explicitly requires knowledge retrieval",
  "rag_tool_name": "query_knowledge_snippets"
}
```

或：

```json
{
  "rag_decision": "skip_rag",
  "rag_reason": "history query only reads user conversation records",
  "rag_tool_name": null
}
```

这些信息会进入 `agent_runtime` / trace 调试链路，便于解释为什么调用或跳过 RAG。

## 当前边界

当前项目没有实现用户上传文档入库链路。

所以 Day89 只保证：

- Agent 有标准 RAG 工具入口
- RAG 可被选择，也可被跳过
- RAG 不覆盖规则引擎的安全结论
- RAG 检索仍使用当前 TF-IDF baseline 和 metadata 过滤

后续如果接入用户文档，需要补：

- 文档上传
- 文档解析
- chunk 切分
- metadata 绑定
- 索引构建
- 用户/租户隔离

这些更适合放到第 17 周 RAG 增强中做。
