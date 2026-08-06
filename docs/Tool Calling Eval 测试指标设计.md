# Tool Calling Eval 测试指标设计

## 目标

Day107 的目标是自动评估 Agent 是否选对工具、少调用工具、不乱调用工具。

这类测试不直接判断“无人机能不能飞”的业务结果，而是评估 Agent 编排过程是否稳定：

- 意图是否识别正确
- 是否调用了期望工具
- 是否没有调用禁止工具
- 缺字段时是否追问
- 越权或工具失败时是否进入正确 fallback

## 测试入口

当前 `/agent/query` 在 `main.py` 中调用：

```python
orchestrate_task_query(payload.query, session_id=payload.session_id, user_id=current_user.id)
```

因此 Tool Calling Eval 可以直接调用 `app.services.task_orchestrator.orchestrate_task_query`，不需要启动 FastAPI 服务。

推荐运行环境：

```powershell
$env:AGENT_RUNTIME_MODE="loop"
$env:NL_PARSER_MODE="rule"
python scripts/tool_calling_eval.py
```

## 样例数据

评测样例放在：

```text
evals/agent/cases.json
```

核心字段：

- `id`：样例唯一标识
- `category`：样例类别，例如 `evaluate`、`recommend`、`compare`、`clarification`
- `input`：用户自然语言输入
- `history_state`：可选历史状态
- `expected_intent`：期望意图
- `expected_tools`：期望调用的工具
- `unexpected_tools`：不应调用的工具
- `expected_fallback`：是否期望进入 fallback
- `expected_missing_fields`：缺字段追问场景中期望追问的字段

## 工具口径

Tool Calling Eval 应以当前 Tool Registry 中真实注册的工具名为准：

```text
evaluate_flight_risk
recommend_flight_windows
compare_flight_locations
query_knowledge_snippets
explain_risk_rules
query_user_history
```

`parse_task`、`fetch_weather`、`merge_context`、`ask_clarification` 更像编排步骤或内部链路，不是当前 `ToolRegistry` 的真实工具。

为了兼容旧样例，脚本会做两件事：

- 将 `evaluate_risk` 归一化为 `evaluate_flight_risk`
- 忽略 `parse_task`、`fetch_weather`、`merge_context` 这类非注册工具

追问场景通过 `agent_runtime.plan_actions` 是否包含 `ask_clarification` 判断。

## 指标定义

### 1. Intent Accuracy

衡量意图识别是否正确。

```text
Intent Accuracy = 意图正确样例数 / 总样例数
```

单条判定：

```python
response.intent == case["expected_intent"]
```

### 2. Tool Selection Accuracy

衡量期望工具是否全部被调用。

```text
Tool Selection Accuracy = 期望工具全部命中的样例数 / 总样例数
```

单条判定：

```python
set(expected_tools).issubset(set(actual_tools))
```

### 3. Exact Tool Match Rate

衡量实际工具集合是否和期望工具集合完全一致。

```text
Exact Tool Match Rate = 实际工具集合等于期望工具集合的样例数 / 总样例数
```

这个指标更严格，早期建议作为观察指标，不建议直接作为硬门禁。

### 4. Extra Tool Call Rate

衡量是否调用了期望之外的工具。

```text
Extra Tool Call Rate = 存在多余工具调用的样例数 / 总样例数
```

### 5. Missing Tool Call Rate

衡量应该调用但没有调用的工具比例。

```text
Missing Tool Call Rate = 缺失工具数量 / 期望工具总数量
```

### 6. Unexpected Tool Violation Rate

衡量明确禁止的工具是否被调用。

```text
Unexpected Tool Violation Rate = 禁止工具被调用次数 / 禁止工具总数
```

### 7. Fallback Accuracy

衡量 fallback 行为是否符合预期。

```text
Fallback Accuracy = fallback 状态符合预期的样例数 / 总样例数
```

实际 fallback 判定：

```python
bool(response.fallback) or not response.success or response.agent_runtime.get("fallback_used")
```

### 8. Clarification Pass Rate

衡量缺字段时是否追问，而不是直接调用业务工具。

通过条件：

- `expected_route == "clarification"` 或存在 `expected_missing_fields`
- `agent_runtime.plan_actions` 包含 `ask_clarification`
- 没有调用 `evaluate_flight_risk`、`recommend_flight_windows`、`compare_flight_locations`
- 返回的缺失字段包含期望缺失字段

### 9. Category Pass Rate

按类别统计通过率，用来定位哪些意图容易选错工具。

```text
Category Pass Rate = 当前类别通过样例数 / 当前类别样例数
```

## 单条样例通过标准

建议 Day107 的单条样例通过标准：

```text
passed =
  intent_pass
  and expected_tools_hit
  and no_unexpected_tools
  and fallback_pass
```

`exact_tool_match` 暂时只作为观察项。

## 报告输出

脚本输出两个文件：

```text
evals/reports/tool_calling_eval.json
evals/reports/tool_calling_eval.md
```

JSON 用于机器读取，Markdown 用于人工查看和面试展示。

报告应包含：

- 总样例数
- 总通过率
- 意图识别准确率
- 工具选择准确率
- 精确工具匹配率
- 多余工具调用率
- 缺失工具调用率
- 禁止工具违规率
- fallback 准确率
- 追问通过率
- 分类通过率
- 失败样例明细

## Day107 验收标准

一条命令可以完成评测：

```powershell
python scripts/tool_calling_eval.py
```

报告能够回答：

- 哪些 case 工具选错了
- 哪些意图容易漏调工具
- 哪些场景出现了多余工具调用
- fallback 和追问行为是否符合预期
- 后续应该优先修复哪个意图类别
