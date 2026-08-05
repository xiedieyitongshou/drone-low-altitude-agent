# Day103 - Chunk 策略与 Rerank

## 目标

把知识召回粒度从“整条知识文档”升级为“chunk 片段”，并在文本相似度之外引入规则 rerank。

## 实现内容

- 新增 `IndexedKnowledgeChunk`，用于表达检索阶段的知识片段。
- 新增 `build_indexed_chunks`，在索引构建阶段按 `knowledge_type` 固定切片。
- BM25 索引从文档级改为 chunk 级。
- Embedding 索引从文档级改为 chunk 级。
- 召回结果保留原始 `knowledge_id`，同时在 metadata 中记录 `chunk_id`、`chunk_type`、`chunk_index`、`chunk_strategy`。
- 新增规则 rerank，对文本召回分数做轻量业务加权。

## 固定切片策略

切片发生在索引构建阶段，不根据每次用户输入动态变化。

- `policy_hint`：按条款、段落切片，对应 `policy_clause`。
- `sop`：按步骤切片，对应 `sop_step`。
- `faq`：按问答对切片，对应 `qa_pair`。
- `risk_advice`：短文本保留完整，长文本按风险块切片，对应 `risk_block`。

这样做的原因：

- 避免每次请求动态切片带来的性能开销。
- 保证同一份知识的切片结果稳定，方便 trace 和 eval。
- 让 BM25、Embedding、Hybrid 可以复用同一套 chunk。

## Rerank 规则

当前规则 rerank 会考虑：

- `review_status=approved`
- `expires_at` 为空，说明未过期
- `knowledge_type` 优先级
- 城市、省份、region 匹配精度
- `task_type` 是否匹配
- `risk_type` 是否命中当前风险标签

规则加权只做轻量修正，不替代 BM25 / Embedding 的主召回分数。

## 与前几天工作的关系

- Day100：BM25 解决关键词精确匹配。
- Day101：Embedding 解决语义匹配。
- Day102：Hybrid 解决两路结果融合。
- Day103：Chunk 解决检索粒度问题，Rerank 解决业务排序问题。

## 面试表达

可以这样解释：

> 项目早期 RAG 是文档级召回，长政策或 SOP 中的局部关键信息容易被稀释。后来我引入了按知识类型的固定 chunk 策略，policy 按条款、SOP 按步骤、FAQ 按问答对、risk advice 保留短块。BM25 和 Embedding 都基于 chunk 建索引，召回后再根据审核状态、时效、地域精确度、任务类型和风险标签做规则 rerank，提升业务相关性，同时保留 `knowledge_id` 和 `chunk_id` 保证可溯源。
