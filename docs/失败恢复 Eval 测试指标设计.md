# 失败恢复 Eval 测试指标设计

## 目标

Day109 的目标是验证 Agent 在工具失败时是否可控、可信、可追踪。

这类 Eval 不依赖真实天气服务、数据库或 RAG 服务故障，而是在测试中使用 fake tool 主动制造失败，检查 Agent 是否正确完成：

- 错误分类
- 恢复策略选择
- fallback 或 deny 决策
- 用户可读说明
- 防止编造业务结论
- trace 错误记录

## 测试入口

`main.py` 中 `/agent/query` 最终调用 `orchestrate_task_query(...)`，但 Day109 更适合直接测试底层 Agent Loop：

```text
AgentState
-> fake ToolRegistry
-> ToolExecutor(trace_recorder=list.append)
-> AgentLoop
-> AgentLoopResult
```

原因：

- 可以稳定注入 `TimeoutError`、`ConnectionError`、`RuntimeError` 等错误
- 不需要等待真实外部服务失败
- 可以精确检查 `failure_type`、`recovery_action`、`retryable` 和 trace

## 失败注入方式

### 1. 抛异常

用于模拟工具执行失败。

```python
lambda payload, context: (_ for _ in ()).throw(TimeoutError("weather timeout"))
```

`ToolRegistry.call(...)` 会捕获异常并转成：

```python
ToolResult(
    success=False,
    tool_name="evaluate_flight_risk",
    error_code="TimeoutError",
    message="weather timeout",
)
```

### 2. ToolSpec 触发权限错误

用于模拟权限不足，不需要 handler 真的执行。

```python
ToolSpec(
    name="query_user_history",
    requires_admin=True,
)
```

用普通用户上下文调用后，应得到：

```text
ADMIN_CONTEXT_REQUIRED
failure_type = permission_denied
recovery_action = deny
```

### 3. 缺认证上下文

工具要求登录，但执行上下文不传 `user_id`。

```python
ToolExecutionContext()
```

应得到：

```text
AUTH_CONTEXT_REQUIRED
failure_type = auth_required
recovery_action = fallback_legacy
```

### 4. 空结果或未找到

通过 `KeyError` 模拟未找到结果。

```python
raise KeyError("not found")
```

应得到：

```text
failure_type = not_found
recovery_action = direct_response
```

## 数据集

数据集路径：

```text
evals/agent/failure_recovery_cases.json
```

每条 case 包含：

- `intent`
- `tool_name`
- `parsed`
- `failure`
- `context`
- `expected`

## 核心指标

### 1. Failure Classification Accuracy

错误分类是否正确。

```text
Failure Classification Accuracy = 分类正确样例数 / 失败样例总数
```

### 2. Recovery Action Accuracy

恢复动作是否正确。

```text
Recovery Action Accuracy = recovery_action 正确样例数 / 失败样例总数
```

当前项目支持：

```text
ask_clarification
fallback_legacy
deny
direct_response
retry
fail_fast
```

### 3. Fallback Decision Accuracy

是否正确使用或拒绝 fallback。

```text
Fallback Decision Accuracy = fallback_used 符合预期样例数 / 总样例数
```

权限类错误尤其要关注：不能通过 legacy fallback 绕过权限。

### 4. Retryability Accuracy

是否正确标记可重试。

```text
Retryability Accuracy = retryable 正确样例数 / 失败样例总数
```

超时和外部依赖失败通常应为 `true`。

### 5. No Fabrication Pass Rate

工具失败后是否没有编造业务结论。

```text
No Fabrication Pass Rate = 未编造样例数 / 需要检查样例总数
```

失败场景中不应输出：

```text
适飞
禁飞
风险较低
可以执行
```

### 6. User Message Quality Pass Rate

最终用户消息是否包含必要限制说明。

```text
User Message Quality Pass Rate = 关键词命中样例数 / 总样例数
```

例如：

- 超时场景：应提示超时或重试
- 权限场景：应提示无权限
- 空结果场景：应提示没有找到
- 参数错误场景：应提示补充信息

### 7. Trace Error Coverage

失败是否记录 error trace。

```text
Trace Error Coverage = 包含 ERROR trace 的失败样例数 / 失败样例总数
```

### 8. Trace Tool Coverage

工具调用链是否被 trace 记录。

```text
Trace Tool Coverage = 包含 TOOL_CALL 的样例数 / 总样例数
```

### 9. Permission Bypass Rate

权限失败后是否错误 fallback 或继续执行。

```text
Permission Bypass Rate = 权限绕过样例数 / 权限类样例总数
```

目标是 `0%`。

### 10. Structured Error Completeness

fallback 输出是否包含结构化字段：

```text
trace_id
run_id
tool_name
failure_type
recovery_action
retryable
errors
```

## 单条 case 通过标准

```text
passed =
  failure_type_pass
  and recovery_action_pass
  and fallback_decision_pass
  and retryable_pass
  and message_keywords_pass
  and no_fabrication_pass
  and trace_error_pass
  and structured_error_pass
```

## 运行命令

```powershell
.\.venv\Scripts\python.exe scripts/failure_recovery_eval.py
```

输出：

```text
evals/reports/failure_recovery_eval.json
evals/reports/failure_recovery_eval.md
```

## Day109 验收标准

- 能稳定构造工具超时、外部依赖失败、权限不足、参数错误、空结果和内部错误
- 能自动判断恢复策略是否正确
- 能证明失败后不编造业务结论
- 能检查 trace 是否记录工具调用和错误
- 报告能指出失败恢复链路的薄弱点
