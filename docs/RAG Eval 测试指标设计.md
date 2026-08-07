# RAG Eval 测试指标设计

## 目标

Day110 与 Day105 联动，目标是把 RAG 检索质量变成可量化报告，而不是只靠人工看召回内容。

重点验证：

- 期望知识是否被召回
- 禁止知识是否没有泄漏
- metadata filter 是否生效
- 低置信和空召回是否进入 fallback
- query rewrite 是否被触发
- Hybrid RAG 是否优于 baseline
- 检索耗时是否可接受

## 测试入口

`main.py` 中 `/knowledge/advice/retrieve` 调用：

```python
retrieve_knowledge_by_request(payload)
```

RAG Eval 直接调用：

```python
retrieve_knowledge_by_request(request, access_context=..., retriever=...)
```

不需要启动 FastAPI。

## 数据集

数据集路径：

```text
evals/rag/cases.json
```

核心字段：

- `query`：用户问题
- `business_context`：任务类型、风险标签、地区
- `access_context`：用户、租户、角色
- `expected_knowledge_ids`：期望命中的知识 ID
- `expected_excluded_knowledge_ids`：不应召回的知识 ID
- `expected_knowledge_types`：期望知识类型
- `expected_chunk_types`：期望 chunk 类型
- `expected_behavior`：fallback、query rewrite、低置信等行为期望
- `top_k`：评测前 K 条结果

## 检索器对比

同一批 case 分别跑：

```text
tfidf
bm25
embedding
hybrid
```

报告输出各 retriever 的独立指标，便于说明 Hybrid 相比 baseline 的提升。

## 核心指标

### 1. Recall@K

```text
Recall@K = 命中的期望知识数 / 期望知识总数
```

用于判断“该召回的有没有召回”。

### 2. Hit Rate@K

```text
Hit Rate@K = 至少命中一个期望知识的 case 数 / 有期望知识的 case 总数
```

比 Recall@K 更宽松。

### 3. MRR

```text
MRR = mean(1 / first_relevant_rank)
```

用于判断相关知识是否排在前面。

### 4. Knowledge Type Accuracy

```text
Knowledge Type Accuracy = 知识类型符合预期的 case 数 / 有知识类型期望的 case 总数
```

例如 SOP 问题应召回 `sop` 或 `risk_advice`。

### 5. Chunk Type Accuracy

```text
Chunk Type Accuracy = chunk 类型符合预期的 case 数 / 有 chunk 类型期望的 case 总数
```

例如：

```text
policy_clause
sop_step
qa_pair
risk_block
```

### 6. Metadata Filter Pass Rate

```text
Metadata Filter Pass Rate = metadata 条件符合预期的 case 数 / metadata case 总数
```

重点检查地域、任务类型、审核状态、有效期、可见性。

### 7. Permission Leakage Rate

```text
Permission Leakage Rate = 召回禁止知识的 case 数 / 权限类 case 总数
```

目标是 `0%`。

### 8. Fallback Pass Rate

```text
Fallback Pass Rate = fallback 行为符合预期的 case 数 / fallback case 总数
```

检查：

```python
response.retrieval_status
response.retrieval_message
response.retrieval_metadata
```

### 9. Query Rewrite Pass Rate

```text
Query Rewrite Pass Rate = 正确触发 query rewrite 的 case 数 / 应触发 rewrite 的 case 总数
```

检查：

```python
response.retrieval_metadata["query_rewritten"]
response.retrieval_metadata["attempts"]
```

### 10. Latency P95

```text
Latency P95 = 检索耗时的 95 分位
```

用于体现 RAG 性能。

## 运行命令

```powershell
.\.venv\Scripts\python.exe scripts/rag_eval.py
```

输出：

```text
evals/reports/rag_eval.json
evals/reports/rag_eval.md
```

## Day110 验收标准

- 一条命令可以跑 RAG Eval
- 能输出 TF-IDF、BM25、Embedding、Hybrid 对比
- 能量化 Recall@K、Hit@K、MRR、metadata filter、权限泄漏、fallback、query rewrite 和延迟
- 报告能指出失败 case 和对应 retriever
