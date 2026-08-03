# Day96 Guardrail 安全回归验收

Day96 的目标是对 Day92-Day95 的 Guardrail 能力做一次集中回归，而不是新增一套独立功能。

## 回归目标

- 验证 Input Guardrail、Tool Guardrail、Output Guardrail 能形成闭环
- 验证工具权限拒绝不会进入 handler
- 验证 Guardrail 拒绝和降级能进入 trace metadata
- 验证 fallback 响应包含用户可读的 `guardrail` 解释
- 验证 DeepSeek 润色前后都有 Output Guardrail 约束

## 覆盖链路

```text
用户输入
  ↓
Input Guardrail
  ↓
Agent Planner / Agent Loop
  ↓
Tool Guardrail
  ↓
ToolExecutor
  ↓
Output Guardrail
  ↓
LLM 润色 / 模板 fallback
  ↓
结构化响应与 trace
```

## 已验证场景

### 输入边界

- 空输入会要求补充问题
- 绕过监管、绕过禁飞、伪造资质等危险意图会被拒绝
- 输入拦截会进入 fallback 响应的 `guardrail` 字段

### 工具边界

- 未登录用户不能调用需要登录的工具
- 普通用户不能调用管理员作用域工具
- 当前用户不能通过 payload 伪造其他 `user_id`
- Tool Guardrail 拦截后 handler 不会执行
- 工具拒绝会写入 trace，并带有 `guardrail_explanation`

### 输出边界

- “绝对安全”“一定能飞”“无需审批”等过度承诺会被拦截
- 涉及政策、审批、管制但缺少知识依据时，不交给 DeepSeek 扩写
- DeepSeek 输出不合规时会被丢弃，并回退模板解释
- 合规 LLM 输出可以正常保留

### 可解释性

- trace metadata 包含 `guardrail_checkpoint`
- trace metadata 包含 `guardrail_action`
- trace metadata 包含 `violation_type`
- trace metadata 包含 `guardrail_user_message`
- fallback output 包含 `guardrail` 解释对象

## 回归测试命令

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_agent_guardrail.py tests/test_agent_loop.py tests/test_tool_executor.py tests/test_agent_fallback.py tests/test_response_explainer_guardrail.py tests/test_tool_registry.py
```

本次执行结果：

```text
36 passed
```

## 验收结论

Day92-Day95 的 Guardrail 能力已经形成基础闭环：

- Day92：完成 Guardrail 三段式架构
- Day93：完成 Output Guardrail 与 DeepSeek 润色联动
- Day94：完成用户权限与工具调用边界
- Day95：完成 Guardrail trace 与拒绝结果可解释
- Day96：完成安全回归验收

当前系统已经能说明：

```text
Agent 为什么没有继续执行；
工具为什么被拒绝调用；
LLM 润色结果为什么被丢弃；
用户为什么收到拒绝或降级响应。
```

这部分能力可以作为“Agent 可控性、可追溯、安全边界”的面试项目亮点。
