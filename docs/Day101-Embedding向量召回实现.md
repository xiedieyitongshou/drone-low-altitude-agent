# Day101 - Embedding 向量召回实现

## 目标

在 BM25 关键词召回之外，补充一条语义向量召回链路，为后续混合检索、召回阈值、无结果兜底和 RAG 评估做准备。

## 实现内容

- 新增 `EmbeddingProvider` 抽象，统一描述向量模型的 `provider`、`model`、`dimension` 和批量向量化方法。
- 新增 `MockEmbeddingProvider`，用本地 deterministic hash embedding 支持离线开发和自动化测试。
- 新增 `LocalEmbeddingKnowledgeStore`，独立生成 `embedding_index.pkl`、`embedding_documents.json`、`embedding_metadata.json`。
- 新增 `EmbeddingKnowledgeRetriever`，通过 `KNOWLEDGE_RETRIEVER=embedding` 接入统一知识检索入口。
- 保留 `bm25` 作为默认检索器，保留 `tfidf` 作为 baseline，避免一次性替换导致效果不可比较。

## 关键设计

### 1. 向量化不是重新训练

当前实现不是训练模型，而是调用一个向量提供器把文本转换成固定维度的向量。真实生产环境可以把 `MockEmbeddingProvider` 替换成云厂商、本地模型或专用 embedding 服务。

### 2. 索引和模型参数绑定

向量索引会记录：

- `provider`
- `model`
- `dimension`
- `knowledge_path`
- `knowledge_mtime`
- `created_at`

如果向量模型、维度或知识库文件发生变化，系统会自动重建索引，避免“知识库用 A 模型向量化、用户问题用 B 模型向量化”导致语义空间错位。

### 3. 召回策略

当前向量召回使用 cosine similarity 计算用户问题与知识片段之间的相似度，并通过 `KNOWLEDGE_EMBEDDING_MIN_SCORE` 控制最低召回阈值。低于阈值的结果不会返回。

### 4. 与已有数据治理兼容

向量召回复用 Day67-Day70 的 metadata 过滤能力：

- `visibility`、`tenant_id`、`user_id` 控制用户可见性。
- `region`、`province`、`city` 控制地区适用范围。
- `task_type`、`risk_type` 控制业务场景匹配。
- `review_status`、`expires_at` 控制审核状态和时效。

## 和 BM25 的关系

- BM25 更适合精确词、政策编号、地名、术语、明确关键词召回。
- Embedding 更适合用户表达和知识文本不完全一致的语义匹配。
- 后续混合检索会把 BM25 与 Embedding 的结果融合，而不是简单二选一。

## 当前边界

- `MockEmbeddingProvider` 只用于工程演示和测试，不代表真实 embedding 模型效果。
- 当前语义扩展是小规模规则表，目的是保证本地可复现，不引入外部 API 成本。
- 真正的召回质量提升需要后续加入真实 embedding 模型、混合检索、重排序和 eval 数据集。
