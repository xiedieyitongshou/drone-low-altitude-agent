# Day102 - 混合检索与 Metadata 加权

## 目标

在 BM25 和 Embedding 两条召回链路之上增加混合检索，解决单一路径召回的局限：

- BM25 擅长政策编号、地名、专业词、关键词精确匹配。
- Embedding 擅长用户表达和知识文本不完全一致时的语义匹配。
- Metadata boost 用业务上下文修正排序，让“更适合当前任务”的知识优先返回。

## 实现内容

- 新增 `HybridKnowledgeRetriever`。
- 通过 `KNOWLEDGE_RETRIEVER=hybrid` 启用混合检索。
- 分别调用 BM25 和 Embedding 召回候选知识。
- 按 `knowledge_id` 合并去重。
- 对两路分数做归一化。
- 叠加 metadata boost 后重新排序。

## 打分公式

当前混合打分公式：

```text
final_score = bm25_score_norm * 0.45
            + embedding_score_norm * 0.45
            + metadata_boost * 0.10
```

其中：

- `bm25_score_norm`：BM25 当前召回结果内的归一化分数。
- `embedding_score_norm`：Embedding 当前召回结果内的归一化分数。
- `metadata_boost`：业务上下文匹配加权，范围为 `0.0 - 1.0`。

## Metadata Boost 规则

当前规则：

- 同城市：`+0.4`
- 同省份：`+0.2`
- 同 region：`+0.1`
- 同任务类型：`+0.2`
- 命中风险标签：`+0.2`
- 最大不超过 `1.0`

城市、省份、region 是递进关系，只取最强匹配。例如命中城市后，不再额外重复计算同省份。

## 设计边界

Metadata boost 不是权限过滤。权限和适用性过滤仍然由 Day67-Day70 的 metadata 过滤完成：

- `visibility`
- `tenant_id`
- `user_id`
- `region`
- `province`
- `city`
- `task_type`
- `risk_type`
- `review_status`
- `expires_at`

混合检索只对已经通过过滤的候选知识做排序增强。也就是说：

- 过滤解决“这条知识能不能被当前用户看到、适不适用当前任务”。
- boost 解决“多条候选知识都可用时，哪条更应该排前面”。

## 输出可解释性

混合检索返回的每条结果会在 metadata 中记录：

- `retriever=hybrid`
- `retrievers`
- `bm25_score`
- `embedding_score`
- `bm25_score_norm`
- `embedding_score_norm`
- `metadata_boost`
- `hybrid_weights`

这样后续 trace 和 RAG eval 可以解释某条知识为什么被排到前面。
