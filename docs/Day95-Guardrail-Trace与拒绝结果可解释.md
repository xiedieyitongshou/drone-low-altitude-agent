# Day95 Guardrail Trace 与拒绝结果可解释

Day95 的目标不是继续堆 Guardrail 规则，而是把 Guardrail 的工作路径沉淀到 trace、日志和结构化响应里。

## 核心目标

- 让每次 Guardrail 检查都能定位到具体检查点
- 让拒绝、降级、追问都有统一解释结构
- 让用户知道为什么请求没有继续执行
- 让开发者能通过 trace 排查是哪一层边界生效
- 为后续 Agent Eval 提供可量化字段

## Guardrail 检查点

当前 Guardrail 覆盖三个阶段：

```text
Input Guardrail
  ↓
Tool Guardrail
  ↓
Output Guardrail
```

对应字段：

- `guardrail_checkpoint`：`input`、`tool`、`output`
- `guardrail_action`：`allow`、`block`、`ask_clarification`、`fallback`
- `guardrail_allowed`：是否通过
- `guardrail_reason`：开发者可读原因
- `guardrail_user_message`：用户可读解释
- `violation_type`：越权或违规类型
- `guardrail_explanation`：统一解释对象

## 统一解释对象

位置：

- `app/agent/guardrail.py`
- `GuardrailExplanation`
- `build_guardrail_explanation`

结构：

```json
{
  "checkpoint": "tool",
  "action": "block",
  "allowed": false,
  "error_code": "TOOL_USER_SCOPE_VIOLATION",
  "reason": "工具输入中的 user_id 与当前登录用户不一致，疑似越权访问。",
  "user_message": "请求中的用户身份与当前登录用户不一致，系统已拒绝越权访问。",
  "violation_type": "payload_user_id_mismatch",
  "tool_name": "query_user_history",
  "metadata": {}
}
```

这样可以把面向开发者的 reason 和面向用户的 user_message 分开。

## Trace 记录

### Input / Output Guardrail

位置：

- `app/agent/loop.py`
- `_record_guardrail_event`

输入拦截和输出降级会记录为 trace event：

- 通过时：`state_update`
- 拦截或降级时：`error`

metadata 中会包含完整 `guardrail_explanation`。

### Tool Guardrail

位置：

- `app/agent/executor.py`
- `_check_tool_guardrail`

工具调用前如果被拒绝，会记录：

- `source=tool_guardrail`
- `tool_name`
- `guardrail_checkpoint=tool`
- `violation_type`
- `failure_type=permission_denied`
- `recovery_action=deny`

handler 不会执行。

## 结构化响应

位置：

- `app/agent/fallback.py`
- `build_agent_fallback_output`

fallback 输出新增：

```json
{
  "guardrail": {
    "checkpoint": "input",
    "action": "block",
    "error_code": "DANGEROUS_INPUT",
    "user_message": "当前输入涉及绕过监管或危险操作，系统已拒绝继续执行。"
  }
}
```

这样前端或演示脚本可以直接展示“为什么被拒绝”，而不是只展示通用失败。

## 当前覆盖场景

- 空输入：要求补充问题
- 危险输入：拒绝绕过监管或危险操作
- 未登录调用受保护工具：进入 fallback
- 普通用户调用管理员工具：拒绝
- payload 伪造其他 `user_id`：拒绝
- LLM 输出过度承诺：丢弃 LLM 输出并回退模板
- 缺少政策依据时：不交给 LLM 扩写

## 测试覆盖

测试文件：

- `tests/test_agent_guardrail.py`
- `tests/test_agent_loop.py`
- `tests/test_tool_executor.py`

运行命令：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_agent_guardrail.py tests/test_agent_loop.py tests/test_tool_executor.py
```
