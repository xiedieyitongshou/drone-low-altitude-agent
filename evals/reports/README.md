# Eval 报告来源

## RAG 当前保存版本

`rag_eval.md` 和 `rag_eval.json` 已在 2026-11-22 从既有验收目录同步为 **2026-11-20 原始结果**，未重新运行，也不是 11 月 22 日的新测试结果。

- 关联实现：`db85a63`，RAG 适用性、逐条相关性、无答案和异常分类。
- 自动 Eval：TF-IDF 7/9、BM25 10/10、Mock Embedding 8/10、Hybrid 11/11；保留失败明细。
- 详细配置、Agent 回放、回归及边界：[RAG 说明](../../docs/RAG检索与无答案处理说明.md)。
- 文件来源及 SHA-256：[验收证据](../../docs/evidence/rag-applicability-20261120/README.md)。

pytest 中的 `run_eval()` 不保存报告；命令行脚本才调用 `write_reports()`。CI 生成的 artifact 也不会自动回写 Git。更新实现后，应分别核对测试和报告来源，不能仅根据报告提交日期判断功能版本。

本次只同步 RAG 报告；本目录其他 Agent/负载报告保留各自原有日期和适用范围。
