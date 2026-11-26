# RAG 检索与无答案处理说明

文档同步日期：2026-11-22。实现与验收依据：2026-11-20 的 RAG 重构，关联提交 `db85a63ae847f7c31b557f261480ee51158f48e5`；原问句和城市透传的前序提交为 `6aa1ee6`。

本文说明现行 RAG 行为，并整理 11 月 20 日已经保存的验收结果。本次文档同步复用原始文件，没有重新执行评测，也没有把其他日期的运行结果并入本报告。Day89、Day99–Day104 文档保留为阶段记录，当前行为以本文和代码为准。

2026-11-26 补充：知识更新采用完整版本构建后原子发布，并新增管理员全局暂停、单条立即撤回和权限收紧保护。操作、存储与验证边界见 [知识发布与检索维护说明](知识发布与检索维护说明.md)。下文历史评测数据保持原记录。

## 入口与职责

- `POST /agent/query` 的知识意图调用 `query_knowledge_snippets`，再进入 `retrieve_knowledge_by_request`。RAG 已接入 Agent。
- `POST /knowledge/advice/retrieve` 可直接提交结构化检索请求。
- 知识问答保留原问句；评估建议等没有原问句的调用，继续根据业务上下文构造查询。
- RAG 提供知识片段和操作建议，不生成或覆盖规则引擎的适飞结论。知识库无答案、检索器异常和飞行评估结论分别表达。

## 11 月 20 日重构后的链路

1. **解析与合并条件。** 复用规则解析、可选 LLM 解析及 Session/Profile 合并。请求接收 `query`、地域、`as_of`、风险、预警、`required_context_fields` 和 `constraint_sources`。缺少明确要求的城市或日期时追问。知识查询的城市不自动成为飞行评估地点。
2. **构造查询。** 有原问句时使用 `query.strip()`，不再向问题拼接通用业务模板词。城市、日期、权限等作为独立过滤条件传递，避免模板词把无答案问题变成看似相关的召回。
3. **适用性过滤。** 检查审核状态、权限、地域、任务、有效日期、风险、结论范围和预警要求。`as_of` 未提供时按应用时区的当前日期判断。有效期边界包含当天。
4. **扩大候选并逐条检查。** 候选上限为 `max(10, top_k * 3)`，逐条检查权限、适用性和分数；有原问句时继续检查主题相关性，最终最多返回 `top_k` 条。
5. **相关性复核。** 排除仅共享城市、任务或通用词的片段，检查具体对象和主题证据。部分匹配候选可由已启用的 LLM 复核，接受结果需要片段内可核对的非空引文；模型不可用或证据不成立时，不据此接受候选。
6. **一次改写重试。** 首轮依据不足时，保留原问题并补同义词、风险原因和预警信息，再检索一次。改写不依赖生成式 LLM，不再追加宽泛的“政策/SOP/FAQ”模板。
7. **返回结果或明确降级。** 仍无足够依据时返回 `fallback` 和原因；索引读取、反序列化等已处理异常返回 `error`，不把系统异常描述成知识库没有答案。

`RAG_CONFIDENCE_THRESHOLD` 默认 `0.2`，是检索分数门槛，不是正确率或概率。通过分数门槛也必须继续满足适用性和相关性检查。

### 预警未知与明确无预警

`warning_types` / `warning_levels` 为 `None` 表示没有给出当前预警状态；显式 `[]` 表示已知没有预警。前者允许回答“黄色预警建议是什么”这种主题问题；后者会过滤要求存在特定预警的执行建议。风险和结论约束同样根据本次实际场景判断。

## 返回状态与诊断字段

| `retrieval_status` | 含义 |
| --- | --- |
| `success` | 首轮找到可接受片段 |
| `rewritten_success` | 改写后的第二轮找到可接受片段 |
| `fallback` | 缺少必要查询条件，或两轮后仍无充分适用依据 |
| `error` | 检索过程出现已处理的系统异常 |

`retrieval_metadata.reason_code` 可包括 `clarification_required`、`no_candidates`、`no_applicable_knowledge`、`low_confidence`、`insufficient_relevance`、`retrieval_error`。每轮 `attempts` 保存查询、分数、阈值、候选数量、接受数量、过滤计数、拒绝原因和 LLM 复核状态。

独立知识问答无答案时，`snippets` 和 `advice` 均为空，并提供 `retrieval_message`。无原问句的评估建议可以保留经过过滤的静态建议；不能把这类建议当成问题已被知识库回答。

无答案是业务兜底，Agent API 回归中可以是 HTTP 200；判断时应结合 `retrieval_status` 和实际内容。11 月 20 日原始回放的部分成功记录中，`reason_code` 仍可能表示存在被过滤候选，不能仅靠该字段把成功记录判为无答案；原始文件按原样保留。

## 检索器与知识来源

默认检索器是 BM25，`KNOWLEDGE_RETRIEVER` 可选 `tfidf`、`bm25`、`embedding`、`hybrid`。Embedding 默认使用本地 `MockEmbeddingProvider`（`hash-ngram-v1`，128 维），不是外部真实语义模型。Hybrid 合并 BM25 和该本地向量分支，做分数融合、metadata 加权及规则重排。

运行时知识管理使用数据库及索引导出的知识源；显式配置、导出文件和种子文件的优先级见 [知识数据说明](../data/knowledge/README.md)。本轮自动 Eval 单独组合种子知识库和 3 条合成夹具，在临时目录构建索引，不等于对当前数据库中的全部知识进行评测。

## 11 月 20 日验收结果

### 自动 RAG Eval

11 个样例按 `retrievers` 字段选择适用检索器，共 40 次运行；不是每个检索器都跑 11 条。知识 ID 按完整 ID 精确匹配。样例覆盖政策、SOP、FAQ、权限正反例、未生效条目、预警适用性和无答案。

| 检索器 | 用例通过 | Recall@K | MRR | 权限泄漏率 | 无答案类 fallback 通过 |
| --- | ---: | ---: | ---: | ---: | ---: |
| TF-IDF | 7/9 | 60.00% | 0.6000 | 0% | 2/2 |
| BM25 | 10/10 | 100.00% | 1.0000 | 0% | 2/2 |
| Mock Embedding | 8/10 | 66.67% | 0.6667 | 0% | 2/2 |
| Hybrid | 11/11 | 100.00% | 0.9286 | 0% | 2/2 |

TF-IDF 漏检大风测绘 SOP、黄色预警主题；Mock Embedding 漏检深圳报备政策、大风测绘 SOP。这些失败保留在 [Markdown 报告](../evals/reports/rag_eval.md) 与 [逐例 JSON](../evals/reports/rag_eval.json) 中。结果不能用于声称所有检索器均通过，或 Hybrid 在真实用户任务上已优于 BM25。

报告的 Rewrite 指标为 N/A：当前数据集没有声明 `second_attempt=query_rewritten` 的计分样例，不代表系统没有改写重试。重试分支另有 `tests/test_rag_fallback.py` 回归覆盖。

### 原有语料的 Agent 主链回放

使用原有知识库，经 Agent API、实际知识工具及 BM25 检索，规则解析、LLM 关闭、隔离 SQLite、无网络：

- 有答案问题：Top-3 目标知识命中 **6/6**。
- 无答案问题：正确兜底 **2/2**，包含具体型号和普通电池寿命问题。
- 保留每例原问句、解析条件、实际工具输入、返回 ID、状态和 Trace ID。

这里的“原有语料”是项目已有知识内容，问题仍为人工选定案例，不是线上用户流量。它与含合成夹具的自动 Eval 分开统计；历史 `2/6` 和 `5/6` 诊断值不作为现版本结果。

[逐例回放](evidence/rag-applicability-20261120/真实知识库Agent回放.json) · [规则结论与无预警传输核验](evidence/rag-applicability-20261120/规则结论与无预警传输核验.json)

### 相邻路径回归

| 验证 | 原始记录 |
| --- | --- |
| Docker 后端回归 | [324 passed](evidence/rag-applicability-20261120/backend-tests.log)，47.87 s |
| 快速 Eval | [4 passed，320 deselected](evidence/rag-applicability-20261120/eval-fast.log)，2.01 s |
| 最终专项回归 | [23 passed](evidence/rag-applicability-20261120/final-focused.log)，1.61 s |
| 同天气切换 RAG | 3 组固定天气中，结论及风险原因一致 |
| 明确无预警条件 | 实际知识工具接收两个空预警列表，未返回要求特定预警的片段 |

当时使用 PostgreSQL 运行后端回归；不能把每个测试都描述为 PostgreSQL 端到端用例。LLM 分支使用模拟响应检查约束及引用校验，未验证真实模型质量。检索耗时来自单次、小样本、本地模拟向量测试，不能推断生产 P95、SLA 或性能提升比例。

## 报告保存与更新方式

11 月 20 日结果原先保存在仓库外的本地验收目录。2026-11-22 将原始报告同步到 `evals/reports/rag_eval.*`，并把回放和日志保存到 [证据目录](evidence/rag-applicability-20261120/README.md)。[manifest.json](evidence/rag-applicability-20261120/manifest.json) 记录复制文件的 SHA-256，未重建历史执行环境，也未补造镜像 ID。

`run_eval()` 返回内存结果；pytest 调用它不写报告。命令行入口调用 `write_reports()` 才更新 Markdown/JSON。CI 手动完整 Eval 上传 artifact，不自动提交回仓库。因此，报告的 Git 更新时间不能代替实现或测试的更新时间。

以后需要重新生成时使用 [RAG Eval 指标与复跑说明](RAG%20Eval%20测试指标设计.md)，同时记录新的日期、代码和知识版本；不要把新运行结果标成 11 月 20 日历史结果。

## 代码和测试入口

- 请求契约：[app/schemas/advice.py](../app/schemas/advice.py)
- 查询与过滤：[app/services/advice_retriever.py](../app/services/advice_retriever.py)、[app/services/vector_knowledge_store.py](../app/services/vector_knowledge_store.py)
- 相关性与重试：[app/services/knowledge_reranker.py](../app/services/knowledge_reranker.py)、[app/services/rag_fallback.py](../app/services/rag_fallback.py)
- Agent 透传、追问、城市隔离、无答案：[tests/test_agent_mixed_orchestration_e2e.py](../tests/test_agent_mixed_orchestration_e2e.py)
- 检索契约及故障：[tests/test_rag_eval.py](../tests/test_rag_eval.py)、[tests/test_rag_fallback.py](../tests/test_rag_fallback.py)、[tests/test_knowledge_business_filter.py](../tests/test_knowledge_business_filter.py)
