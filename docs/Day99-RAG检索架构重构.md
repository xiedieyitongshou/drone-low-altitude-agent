# Day99 RAG 检索架构重构

Day99 的目标是把当前 TF-IDF 检索从业务入口中抽离出来，为后续 BM25、Embedding 和 Hybrid Retrieval 做准备。

## 当前问题

原有链路中，`retrieve_knowledge_by_request` 直接创建 `LocalVectorKnowledgeStore`：

```text
业务入口
  ↓
advice_retriever
  ↓
LocalVectorKnowledgeStore / TF-IDF
  ↓
snippets
```

这种写法能跑通 baseline，但后续新增 BM25、Embedding 或 Hybrid 时，容易让业务入口持续膨胀。

## 重构目标

- 业务入口只依赖统一 Retriever 接口
- 当前 TF-IDF 保留为 baseline retriever
- 后续新增检索器不需要改业务入口
- Day67-Day70 的 metadata 过滤仍然保留在召回链路中
- 输入输出结构保持兼容

## 当前实现

新增文件：

- `app/services/knowledge_retrievers.py`

核心结构：

```python
class KnowledgeRetriever(Protocol):
    name: str

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        access_context: KnowledgeAccessContext | None = None,
        business_context: KnowledgeBusinessContext | None = None,
    ) -> list[RetrievedKnowledgeSnippet]:
        ...
```

当前 baseline：

```python
TfidfKnowledgeRetriever
```

它内部继续复用：

- `LocalVectorKnowledgeStore`
- `build_retrieval_query`
- `is_document_visible`
- `is_document_applicable`

## 新链路

```text
KnowledgeRetrievalRequest
  ↓
advice_retriever 构造 AdviceRetrievalContext
  ↓
advice_retriever 构造 KnowledgeBusinessContext
  ↓
build_knowledge_retrieval_query
  ↓
KnowledgeRetriever.retrieve
  ↓
TfidfKnowledgeRetriever baseline
  ↓
LocalVectorKnowledgeStore
  ↓
metadata filter + TF-IDF score
```

## 保留的过滤边界

检索器调用仍然传入：

- `access_context`
  - `user_id`
  - `tenant_id`
  - `role`
- `business_context`
  - `task_type`
  - `risk_tags`
  - `region`
  - `province`
  - `city`

因此 Day67-Day70 的数据治理字段仍然在召回阶段生效：

- `visibility`
- `user_id`
- `tenant_id`
- `review_status`
- `effective_at`
- `expires_at`
- `region`
- `province`
- `city`
- `task_type`
- `risk_type`

## 后续扩展方式

Day100 可以新增：

```text
Bm25KnowledgeRetriever
```

Day101 可以新增：

```text
EmbeddingKnowledgeRetriever
```

Day102 可以新增：

```text
HybridKnowledgeRetriever
```

业务入口仍然只接收：

```text
KnowledgeRetriever
```

## 测试覆盖

新增测试：

- `tests/test_knowledge_retrievers.py`

覆盖点：

- `retrieve_knowledge_by_request` 可以注入自定义 retriever
- `access_context` 会原样传入 retriever
- `business_context` 会保留任务类型、风险标签和地域信息
- query 构造格式保持兼容

运行命令：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_knowledge_retrievers.py tests/test_knowledge_access_filter.py tests/test_knowledge_business_filter.py
```
