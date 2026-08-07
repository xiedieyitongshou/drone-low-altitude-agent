# Day111 Eval 接入测试体系与 CI 预留

## 目标

Day111 的目标是把 Day107-Day110 的评测脚本接入测试体系，让 Agent 行为具备持续回归能力。

这里的重点不是新增业务功能，而是建立质量门禁：

- 修改 Agent Planner 后，能发现工具选择退化
- 修改 Session Memory 后，能发现多轮状态污染
- 修改失败恢复策略后，能发现 fallback 或 trace 退化
- 修改 RAG 检索后，能发现召回、权限过滤或延迟退化

## 快速回归与完整评测

### 快速回归集

快速回归集用于日常开发和 CI。

特点：

- 运行快
- 不访问真实天气 API
- 不依赖真实大模型输出
- 失败原因清晰
- 只检查关键质量底线

当前接入：

```text
tests/test_eval_regression.py
```

运行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_eval_regression.py -q
```

也可以按 marker 运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m eval_fast -q
```

### 完整评测集

完整评测集用于阶段验收、发版前检查和报告生成。

特点：

- case 更多
- 指标更完整
- 会生成 JSON/Markdown 报告
- 允许运行更久

运行命令：

```powershell
.\.venv\Scripts\python.exe scripts/tool_calling_eval.py
.\.venv\Scripts\python.exe scripts/multi_turn_state_eval.py
.\.venv\Scripts\python.exe scripts/failure_recovery_eval.py
.\.venv\Scripts\python.exe scripts/rag_eval.py
```

报告输出：

```text
evals/reports/tool_calling_eval.json
evals/reports/multi_turn_state_eval.json
evals/reports/failure_recovery_eval.json
evals/reports/rag_eval.json
```

## 质量门禁

门禁测试不是证明功能完美，而是证明当前版本没有低于最低质量线。

### Tool Calling 门禁

当前门禁：

```text
intent_accuracy >= 0.95
tool_selection_accuracy >= 0.90
unexpected_tool_violation_rate <= 0.10
missing_tool_call_rate <= 0.05
```

含义：

- 意图不能大面积识别错误
- 关键工具不能漏调
- 不应出现明显乱调工具

### Multi-turn State 门禁

当前门禁：

```text
state_inheritance_accuracy >= 0.95
state_override_accuracy >= 0.95
tool_input_consistency >= 0.95
context_pollution_rate == 0
session_isolation_pass_rate >= 0.95
```

含义：

- 应继承的字段必须稳定继承
- 用户修改的字段必须覆盖旧状态
- 工具输入必须和合并后的任务状态一致
- 不同 session/user 不能串状态

### Failure Recovery 门禁

当前门禁：

```text
failure_classification_accuracy >= 0.95
recovery_action_accuracy >= 0.95
fallback_decision_accuracy >= 0.95
trace_error_coverage >= 0.95
permission_bypass_rate == 0
```

含义：

- 错误类型必须正确分类
- 恢复策略必须正确
- 权限失败不能被 fallback 绕过
- 工具失败必须可追踪

### RAG Eval 门禁

快速回归只跑 `hybrid` retriever。

当前门禁：

```text
recall_at_k >= 0.70
hit_rate_at_k >= 0.70
metadata_filter_pass_rate >= 0.95
permission_leakage_rate == 0
p95_latency_ms <= 500
```

含义：

- 关键知识必须能召回
- 权限和 metadata filter 不能退化
- 检索耗时不能明显失控

说明：

当前 RAG 数据集里 SOP、FAQ 和 fallback case 仍暴露召回质量问题，所以快速门禁只卡核心底线，不把完整 pass rate 作为硬门禁。

## CI 预留命令

Day113/Day114 接入 GitHub Actions 时，建议使用：

```yaml
- name: Run backend tests
  run: .\.venv\Scripts\python.exe -m pytest -q

- name: Run fast eval gates
  run: .\.venv\Scripts\python.exe -m pytest -m eval_fast -q
```

Linux runner 上命令改为：

```bash
python -m pytest -q
python -m pytest -m eval_fast -q
```

## 失败处理原则

如果门禁失败：

- 先看失败指标，不要只看总 pass rate
- Tool Calling 失败优先查 parser、business_routes、planner
- Multi-turn 失败优先查 session_memory、context_manager
- Failure Recovery 失败优先查 failure_policy、fallback、ToolExecutor trace
- RAG 失败优先查知识库数据、metadata filter、retriever 权重、fallback 阈值

## Day111 完成标准

- Eval 快速回归可通过 pytest 运行
- 快速回归和完整评测边界清晰
- 文档说明本地运行和 CI 预留命令
- 关键指标有明确阈值
- 修改 Agent 核心逻辑后，可以自动发现行为退化
