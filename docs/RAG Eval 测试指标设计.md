# RAG Eval 测试指标设计

## 目标

同步日期：2026-11-22。本文按 11 月 20 日重构后的评测脚本说明指标；实现和已有结果见 [RAG 检索与无答案处理说明](RAG检索与无答案处理说明.md)。本次沿用当日原始报告，不重新评测。

重点验证：

- 期望知识是否被召回
- 禁止知识是否没有泄漏
- metadata filter 是否生效
- 低置信和空召回是否进入 fallback
- query rewrite 是否被触发
- 各检索器在适用样例中的表现及失败原因
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

当前有 11 个案例。脚本将 `data/knowledge/advice_rules.json` 与 `evals/rag/fixtures.json` 的 3 条合成夹具合并，在临时目录建立索引；不使用运行中的数据库知识库或已有索引。原有语料的 Agent 回放另存于 [验收证据](evidence/rag-applicability-20261120/README.md)，不混入本组指标。

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
- `retrievers`：可选，限定适用检索器；未填写时用于全部检索器

当前全部 `top_k` 为 3。知识 ID 精确匹配，不再以 ID 前缀或子串命中。FAQ 夹具不适用于 TF-IDF，Hybrid metadata 案例仅用于 Hybrid，因此 TF-IDF / BM25 / Embedding / Hybrid 分别运行 9 / 10 / 10 / 11 条，共 40 次。

## 检索器对比

同一批 case 分别跑：

```text
tfidf
bm25
embedding
hybrid
```

报告输出各 retriever 的独立指标。由于适用样例集合不同，不能直接用总通过率断言 Hybrid 优于其他方案。Embedding 默认是本地 Mock（`hash-ngram-v1`，128 维），本结果不代表真实语义模型。

## 核心指标

### 1. Recall@K

```text
Recall@K = 命中的期望知识数 / 期望知识总数
```

先按每个案例计算，再对有 `expected_knowledge_ids` 的案例取平均。没有期望正例 ID 的权限反例、无答案案例不进入 Recall@K、Hit@K 和 MRR 的分母，但仍参与用例通过率。

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

当前按案例中声明的所有期望类型是否出现在结果中判断；无类型期望的案例不进入该指标分母。

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
Metadata Filter Pass Rate = metadata_filter_pass 为真的 case 数 / 本检索器全部运行 case 数
```

逐例检查禁止 ID 是否泄漏，以及显式 `expected_metadata` 是否至少有一条结果满足。没有显式 metadata 断言的案例也可能通过，因此 `100%` 不能解释为已穷举地域、有效期、权限等全部组合。具体覆盖由案例和单元测试共同说明。

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

当前 11 条案例没有声明 `second_attempt=query_rewritten`，因此报告该项为 `N/A`。这不是改写逻辑不存在或测试失败；两轮重试另有 `tests/test_rag_fallback.py` 回归。

### 10. Latency P95

```text
Latency P95 = 检索耗时的 95 分位
```

脚本对本次各 case 的检索耗时排序，使用 `round(0.95 * (n - 1))` 对应项。每个检索器只有 9–11 个样本，最大值可能恰好也是这里的 P95；不能外推生产延迟、并发能力或性能优化收益。

### 11. 用例通过率与无答案

`pass_rate` 要求该例的知识 ID、类型、metadata、权限、fallback、安全和检索器来源等适用断言全部通过。它不等于生成答案准确率。

当前两个 `category=fallback` 案例要求返回 `fallback` 且片段为空。索引异常应返回 `error/retrieval_error`，由故障单元测试覆盖，不能与知识库无答案混算。完整运行中看到被重试或被过滤的候选，也不等于最终误返回。

## 运行命令

```powershell
$env:LLM_ENABLED = 'false'
$env:RAG_CONFIDENCE_THRESHOLD = '0.2'
.\.venv\Scripts\python.exe scripts/rag_eval.py
```

这是以后需要复跑时的命令，本次同步未执行。若需保留当前历史结果，先将新报告写到独立目录，例如追加 `--report-dir data/eval-reports/rag-new-run`；核对后再更新仓库报告及来源清单。

输出：

```text
evals/reports/rag_eval.json
evals/reports/rag_eval.md
```

pytest 与保存报告的区别：`run_eval()` 只返回内存对象，`main()` 才调用 `write_reports()`。因此测试通过不会自动更新上述文件。手动 CI 生成并上传 artifact，也不会自动提交报告回 Git。

## 已保存结果与验收范围

当前报告是 2026-11-20 原始结果，于 2026-11-22 同步入库：TF-IDF 7/9、BM25 10/10、Mock Embedding 8/10、Hybrid 11/11。原始结果含四条漏检，未把失败删除或改成通过。详情见 [报告来源](../evals/reports/README.md) 与 [逐例结果](../evals/reports/rag_eval.json)。

- 一条命令可以跑 RAG Eval
- 能输出 TF-IDF、BM25、Embedding、Hybrid 对比
- 能量化 Recall@K、Hit@K、MRR、metadata filter、权限泄漏、fallback、query rewrite 和延迟
- 报告能指出失败 case 和对应 retriever

快速门禁以 `tests/test_eval_regression.py` 为准；BM25 完整样例通过和 fallback 行为另由 `tests/test_rag_eval.py` 检查。上述小样本工程验收不能代替真实用户需求、政策有效性或真实模型效果验证。
