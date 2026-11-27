# Eval 断言审计验收记录

日期：2026-11-27。问题基线：`0a39d6046382fe7e8f7c49ce66c56c889cf45fef`。本记录对应其后的断言整改，使用 [summary.json](summary.json) 中的源文件 SHA-256 标识本轮测试实现；指纹将 CRLF 归一为 LF，方便跨平台核对。整改后的实现应按源码指纹及包含本记录的提交核对，不能用问题基线提交代替。

## 本地结果

| 范围 | 结果 | 条件 |
|---|---|---|
| 完整后端回归 | 537 passed、5 skipped、12 warnings，225.89 秒 | 隔离 SQLite，关闭外部模型/天气凭据；五个 live 场景按默认设置跳过 |
| Tool Calling | 九条主样例全部通过，包含一轮补参续接 | 实际 Loop/Executor/Guardrail，业务 handler 为夹具 |
| 多轮状态 | 七条对话、十五轮全部通过 | 规则解析、上下文和计划参数回归，不执行业务 handler |
| 失败恢复 | 七类全部通过；两类权限/缺身份场景的 handler 调用均为 0 | 实际失败策略与受控 handler 异常；Trace 仅在内存 |
| RAG BM25 / Hybrid | 10/10、11/11，均满足门禁 | 临时索引与固定语料，模型相关性复核关闭 |
| RAG 对照组 | TF-IDF 7/9、Mock Embedding 8/10 | 保留漏检，不计作生产检索器完整通过 |
| 模型场景框架 | 五类离线夹具通过，覆盖 JSON 和 Schema 两种注入 | 使用实际业务工具和临时数据库；没有真实 DeepSeek 效果或性能结论 |

所有检索器的实际指标和延迟见摘要 JSON。RAG 的 P95 是本机固定语料测量，非生产 SLA。后端现有序列化和依赖警告未在本轮修改。

## 负例验证的判定缺口

- 错工具、错实参、上一轮非追问或仍缺参时，不能算续接成功。
- 权限拒绝后执行了 handler，或缺少执行证据时，权限门禁失败。
- 空 Trace、非法布尔值、空错误列表不算结构完整；嵌套业务结论也会使故障样例失败。
- RAG 即使 fallback 状态和泄露统计正常，仍有禁止片段或授权正例无结果时，关键类别门禁失败。
- 空数据集、空对话、重复 ID、删除必要对话均不能形成完整基线通过。

完整映射见 [Eval 断言审计](../../Eval质量门禁与断言审计.md)。模型场景与观测指标见 [DeepSeek 验收方案](../../真实DeepSeek回归验收方案.md)。

## 复现与证据范围

从项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m eval_fast -q
.\.venv\Scripts\python.exe -m pytest tests/test_eval_cli.py tests/test_multi_turn_state_eval.py tests/test_failure_recovery_eval.py tests/test_rag_eval.py tests/test_deepseek_harness.py -q
```

完整 API 回归需配置独立测试数据库并执行迁移。Windows 沙箱若阻断异步事件循环的本机 socketpair，应使用允许本机通信的离线测试环境，不能把未进入业务断言的阻塞记作通过。

本机完整日志位于 `data/eval-reports/eval-integrity-backend-20261127.log`，四组新报告位于 `data/eval-reports/eval-integrity-20261127/`。这些本机路径被 Git 忽略；本目录仅保存技术摘要与源码指纹，不包含配置文件、模型原始私有上下文或个人复盘材料。远程 Actions 和真实模型验收分别核验，不从本地结果推定。
