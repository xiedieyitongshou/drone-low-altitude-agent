# Eval 报告来源

## Tool Calling 当前保存版本

`tool_calling_eval.md` 和 `tool_calling_eval.json` 于 **2026-11-27** 按本轮 Eval 门禁修补后的工作区重新生成：九条主样例 **9/9**，缺参样例另包含一轮补参续接；追问、续接、Guardrail 和 fallback 均通过。

- 执行模式：`runtime_fixture`，实际执行规则 Parser、Context Merge、AgentLoop、ToolExecutor 和 Guardrail，业务 handler 与 Trace 存储使用夹具。
- 权限负例向候选工具载荷注入其他用户 ID，断言拒绝和 handler 未执行；不是自然语言目标用户解析能力的证明。
- 工具超时为 handler 中显式抛出的故障，报告保留注入信息。该组不验证真实天气、业务数据库或模型接入质量。
- 现行门禁与本次本地验收：[CI/CD 说明](../../docs/CI-CD说明.md#本轮修补与验证)。真实 DeepSeek 专项待明确外发授权后执行，离线模型夹具结果单独计数。

## RAG 当前保存版本

`rag_eval.md` 和 `rag_eval.json` 已在 2026-11-22 从既有验收目录同步为 **2026-11-20 原始结果**，未重新运行，也不是 11 月 22 日的新测试结果。

- 关联实现：`db85a63`，RAG 适用性、逐条相关性、无答案和异常分类。
- 自动 Eval：TF-IDF 7/9、BM25 10/10、Mock Embedding 8/10、Hybrid 11/11；保留失败明细。
- 详细配置、Agent 回放、回归及边界：[RAG 说明](../../docs/RAG检索与无答案处理说明.md)。
- 文件来源及 SHA-256：[验收证据](../../docs/evidence/rag-applicability-20261120/README.md)。

pytest 中的 `run_eval()` 不保存报告；命令行脚本才调用 `write_reports()`。CI 生成的 artifact 也不会自动回写 Git。更新实现后，应分别核对测试和报告来源，不能仅根据报告提交日期判断功能版本。

2026-11-22 的同步仅涉及 RAG；Tool Calling 后于 2026-11-27 更新。其他 Agent/负载报告保留各自原有日期和适用范围，不能将本目录所有报告视为同一批运行。
