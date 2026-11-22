# RAG 适用性与无答案验收证据

结果日期：2026-11-20。同步入库日期：2026-11-22。关联实现提交：`db85a63`。

这些文件来自此前保存的本地 RAG 验收目录，按字节复制，未重跑测试。原始文件生成于关联提交创建之前；没有据此断言当时运行于该提交的干净检出，也没有补造镜像 ID 或运行时版本。

| 文件 | 用途 |
| --- | --- |
| [真实知识库Agent回放.json](真实知识库Agent回放.json) | 原有语料经 Agent API 回放：有答案 6/6，无答案 2/2；含配置和语料哈希 |
| [规则结论与无预警传输核验.json](规则结论与无预警传输核验.json) | 3 组同天气规则结论不变，以及明确无预警的工具参数 |
| [backend-tests.log](backend-tests.log) | 当时后端回归 324 passed |
| [eval-fast.log](eval-fast.log) | 当时快速 Eval 4 passed、320 deselected |
| [final-focused.log](final-focused.log) | 当时专项回归 23 passed |
| [RAG Markdown 报告](../../../evals/reports/rag_eval.md) | 四种检索器汇总及失败案例 |
| [RAG JSON 报告](../../../evals/reports/rag_eval.json) | 40 次自动 Eval 的逐例结果 |
| [manifest.json](manifest.json) | 上述 7 份复制文件的路径、字节数和 SHA-256 |

结果解释与边界见 [RAG 检索与无答案处理说明](../../RAG检索与无答案处理说明.md)。LLM 使用关闭或模拟配置，Embedding 是本地 Mock；原有语料回放与带合成夹具的自动 Eval 分开统计。

以后生成新的 `evals/reports/rag_eval.*` 时，应另行保留历史副本并更新来源说明，避免将此清单中的历史哈希误用于新报告。
