# Eval 质量门禁与断言审计

更新日期：2026-11-27。问题基线：`0a39d60`。本文说明固定 Eval 基线的验收标准、断言缺口、整改和证据，适用于代码回归与 CI。真实模型接入另按 [DeepSeek 验收方案](真实DeepSeek回归验收方案.md) 执行。

当前采用两层验证：确定性 Eval 用固定数据检查解析、状态、工具约束、失败恢复及检索；真实 DeepSeek 专项检查模型接入后参数、业务工具、会话与数据库状态的一致性。通过某组固定样例，仅证明对应场景在给定条件下达标。

## 1. 执行范围

| 专项 | 实际执行内容 | 替代或隔离的依赖 |
|---|---|---|
| Tool Calling | 规则 Parser、Context Merge、AgentLoop、ToolExecutor、Guardrail | 业务 handler 为夹具，Trace 不落业务库；权限负例显式注入伪造用户参数 |
| 多轮状态 | 实际规则解析、上下文合并、Planner、临时 Session 的继承与覆盖 | 不执行业务 handler，不代表业务写库或模型效果 |
| 失败恢复 | 实际 AgentLoop、ToolExecutor、Guardrail 和失败策略 | handler 注入异常；Trace 仅在内存记录，不写入业务库 |
| RAG | 实际检索、适用性/权限过滤、相关性判定及无答案处理 | 种子知识与合成夹具在临时目录建索引；关闭模型相关性复核，Embedding 为模拟向量 |

## 2. 硬门禁与统计口径

固定基线由 [快速门禁测试](../tests/test_eval_regression.py) 执行。单例通过要求该例声明的关键检查全部通过；总通过率以完整通过的样例数除以执行样例数，多轮以轮次统计。

| 专项 | 指标与分母 | 当前要求 |
|---|---|---|
| Tool Calling | 总通过率：主样例；追问、续接、Guardrail：各自适用样例 | 总通过率、追问、续接、Guardrail、fallback 与四类关键场景均为 100%；禁止工具违规为 0；至少九条主样例 |
| Tool Calling | 意图和工具选择：主样例；漏调：期望工具数 | 意图准确率 ≥95%，工具选择 ≥90%，漏调 ≤5%；保留原分项作定位 |
| 多轮状态 | 总通过率：轮次；续接：声明补参续接的轮次；修改/失效：有相应预期的轮次 | 非空；总通过率、续接、修改字段及工具失效准确率均为 100% |
| 多轮状态 | 继承、覆盖、工具实参：声明的字段；污染/隔离：适用轮次 | 继承、覆盖、工具实参、隔离 ≥95%；污染率为 0；保留七条固定对话案例 |
| 失败恢复 | 总通过率、分类、恢复、重试、错误结构和输出检查：故障样例 | 非空；总通过率、重试判断、结构完整、不生成业务决策均为 100%；分类、恢复、fallback、Trace 错误覆盖 ≥95% |
| 失败恢复 | 权限绕过：权限拒绝和缺少身份上下文两类样例 | 为 0；必须拒绝、无 legacy 回退、handler 未执行且无业务数据返回 |
| RAG | Recall：有目标 ID 的样例逐例召回率均值；Hit：这些样例中至少命中一条的比例 | 两项均 ≥70% |
| RAG | metadata filter：适用检索器的全部样例；泄露：权限样例中出现禁止 ID 的比例 | filter ≥95%；泄露为 0；权限类别逐例通过 |
| RAG | fallback：无答案样例的状态判断；类别通过率：该类全部检查 | fallback 状态和 fallback 类别通过率均为 100%，防止状态正确但仍返回禁止片段 |
| RAG | 延迟：该检索器适用样例的检索耗时 | P95 ≤500ms；本地固定语料指标，不是线上 SLA |

RAG 默认命令对 BM25、Hybrid 执行门禁；TF-IDF、Mock Embedding 的漏检作为对照列入报告。单独选择其他检索器时，同样使用公开阈值。MRR、检索类型/切块命中、平均延迟等继续保留用于分析，未全部设为独立硬阈值。

## 3. 本轮修复的错误通过路径

| 编号 | 原判定缺口 | 整改后的检查 | 对应验证 |
|---|---|---|---|
| E01 | 续接指标只要出现 `call_tool` 和工具名即可为真 | 同一用户/会话上一轮须为追问；目标工具、状态、继承字段及实参均正确，且无缺参 | 错工具、错参数、上一轮非追问、仍有缺参四个负例 |
| E02 | 多轮解析出错且无意图时，借用样例的期望意图充当实际值 | 无意图保留为 `unknown`，不能使用答案补实际结果；明确声明缺参时按集合精确匹配 | 缺参额外追问负例及正常多轮基线 |
| E03 | 权限指标只看是否进入 legacy 回退 | 记录 handler 调用；检查明确拒绝、handler 未执行、无业务数据，缺少执行证据也失败 | 权限/缺身份样例被伪造为已执行 handler 时必须失败 |
| E04 | 错误结构只看字段名存在 | 标识字段须有值；`retryable` 须为布尔值；`errors` 须有错误记录 | 空 trace、空 run、字符串布尔值及空错误列表负例 |
| E05 | 失败输出仅通过少量关键词判断是否产生错误结论 | 同时检查结构化业务决策字段，禁止在故障输出或工具数据中夹带适飞、风险或推荐窗口结果 | 嵌套 `advice.allow_cruise` 的负例 |
| E06 | RAG 的 fallback 状态正确即可使聚合指标通过 | 无答案和权限类别须完整通过各自单例检查 | fallback 仍有片段、授权正例无结果两个负例；原聚合状态/泄露指标仍可为正常值，新门禁必须失败 |
| E07 | 空对话可能不产生轮次；删关键场景后剩余样例仍全通过 | CLI 核对对话数与执行 ID，拒绝空对话或重复 ID；CI 固定基线检查必要案例及重复标识 | 空对话、重复 ID、删除追问对话后仍有 100% 已执行通过率三个负例 |

“不生成业务决策”仍是结构化字段与有限关键词检查，不等于通用语义事实核验。权限统计主要覆盖数据集声明的拒绝条件；完整权限实现还由业务 API 与工具专项测试验证。

## 4. 关键场景如何进入门禁

1. 多轮基线包含地点、时段、任务类型修改，补参续接，意图切换，污染检查和会话隔离。
2. 失败基线包含超时、外部依赖、非法输入、权限、缺身份、无结果和内部错误。
3. RAG 基线必须保留私有知识拒绝/授权正例，以及两条无答案样例。
4. CI 显式检查必要案例 ID；增加或替换固定场景时同步审核这份案例要求。
5. 自定义 `--cases` 可用于局部诊断；局部评测成功不替代固定基线的完整 CI 验收。

### 失败退出与报告

- Tool Calling、多轮和失败恢复的用例失败或空集返回 `1`，仍生成 JSON/Markdown。
- 多轮 CLI 还拒绝未执行的空对话和重复对话标识，即使其余轮次通过率为 100%。
- RAG 未达到所选门禁阈值时返回 `1`。
- CI 和 Docker 完整 Eval 汇总前面所有失败，不用最后一条命令的成功覆盖失败；CI 使用 `always()` 上传已有报告。
- [CLI 回归](../tests/test_eval_cli.py) 验证四个命令的错误预期、空集以及多轮结构错误。

## 5. 复现入口

在已安装依赖的项目根目录执行：

```powershell
$env:LLM_ENABLED="false"
$env:NL_PARSER_MODE="rule"
.\.venv\Scripts\python.exe -m pytest -m eval_fast -q
.\.venv\Scripts\python.exe -m pytest tests/test_multi_turn_state_eval.py tests/test_failure_recovery_eval.py tests/test_rag_eval.py tests/test_eval_cli.py -q
```

报告脚本可使用同一个新目录保存本次结果：

```powershell
.\.venv\Scripts\python.exe scripts/tool_calling_eval.py --report-dir data/eval-reports/eval-integrity-run
.\.venv\Scripts\python.exe scripts/multi_turn_state_eval.py --report-dir data/eval-reports/eval-integrity-run
.\.venv\Scripts\python.exe scripts/failure_recovery_eval.py --report-dir data/eval-reports/eval-integrity-run
.\.venv\Scripts\python.exe scripts/rag_eval.py --report-dir data/eval-reports/eval-integrity-run
```

`run_eval()` 在内存计算；只有报告入口写文件。每次报告应保留测试日期、代码版本、工作区变更和执行范围，区分历史结果、固定夹具结果及模型结果。

## 6. 验收状态与边界

前一轮 `0a39d60` 的本地记录为后端 519 passed、5 skipped，Tool Calling 9/9、多轮 15/15、失败恢复 7/7，BM25 10/10、Hybrid 11/11。这里的五个跳过项是真实模型场景，不计为模型通过。

本轮完整回归为 **537 passed、5 skipped**；五个跳过项仍为 live 模型场景。四组新报告和源文件指纹见 [审计证据索引](evidence/eval-integrity-20261127/README.md)，运行接入见 [CI/CD 说明](CI-CD说明.md#eval-断言完整性补充审计)。不将 CI 配置存在等同于远程 Actions 已通过。

进一步验证分别记录：模型正常输出与受控故障、同一模型重复运行波动、Token/费用采集、实际 HTTP 和 PostgreSQL/Redis 的集成场景。它们不由本组固定 Eval 结果推定完成。
