# Day104 - RAG 空召回、低置信与 Query Rewrite

## 目标

处理知识库召回为空、召回分数过低的问题，避免 Agent 在缺少可靠依据时强行编造政策或建议。

## 实现内容

- 新增 RAG 置信度判断。
- 支持 `RAG_CONFIDENCE_THRESHOLD` 配置最低可信分数，默认 `0.2`。
- 第一次召回为空或低置信时，基于任务类型、地区、风险标签、预警信息重写 query。
- 使用重写后的 query 进行第二次召回。
- 二次召回仍失败时，返回保守 fallback，不返回低置信 snippets。
- 在响应中记录 `retrieval_status`、`retrieval_message`、`retrieval_metadata`，便于后续 trace 可视化。

## 判断逻辑

当前不使用严格意义上的召回率，因为在线查询时没有标准答案集合。工程上用以下信号判断结果是否可信：

- 是否有召回结果。
- `top_score` 是否达到阈值。
- 两次召回的状态、分数、数量是否可追踪。

状态包括：

- `success`：首次召回可信。
- `rewritten_success`：首次失败，query rewrite 后召回可信。
- `fallback`：两次召回都为空或低置信。

## Query Rewrite 策略

重写 query 不依赖大模型，采用可解释的模板方式补充上下文：

- `task_type`
- `risk_tags`
- `risk_reasons`
- `warning_types`
- `warning_levels`
- `province`
- `city`
- `region`

这样做的原因是当前项目是求职项目，数据规模有限，引入大模型重写 query 的收益不稳定，而且会增加成本和不可控性。

## Fallback 策略

如果二次召回仍然失败：

- 不返回低置信 snippets。
- 不把不可靠内容作为政策依据。
- 返回保守说明，提示用户补充地区、任务类型、风险原因或政策关键词。

## 与前序工作的关系

- Day100：BM25 提供关键词召回。
- Day101：Embedding 提供语义召回。
- Day102：Hybrid 融合两路召回结果。
- Day103：Chunk 提升召回粒度，Rerank 提升业务排序。
- Day104：解决召回为空或低置信时的工程兜底。

## 面试表达

可以这样说明：

> 我没有让 RAG 在低置信时强行输出依据，而是设计了空召回和低置信检测。第一次召回失败后，会用任务类型、地区、风险标签和预警信息做一次可解释的 query rewrite，再进行二次召回。如果仍失败，系统返回保守说明或触发追问，不编造政策依据。同时每次尝试的 query、top score、结果数量和失败原因都会写入响应 metadata，后续可以接入 trace。
