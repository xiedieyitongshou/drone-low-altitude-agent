# Day92 Guardrail 架构设计

Day92 的目标是为 Agent Runtime 增加强制边界层，而不是一次性写满所有安全规则。

## 设计目标

- 控制 Agent 的输入边界、工具调用边界和最终输出边界
- 将 Guardrail 固定接入运行时，而不是交给 Agent 自己决定是否调用
- 为后续工具权限、RAG metadata 权限、安全输出模板和 Eval 回归预留扩展点
- 将拦截、降级、追问等行为写入日志和 trace，保证可解释、可溯源

## 三个检查点

### Input Guardrail

位置：

```text
用户输入 → Input Guardrail → Planner
```

职责：

- 拦截空输入
- 拦截明显要求绕过监管、绕过审批、伪造资质的危险意图
- 需要补充信息时返回追问动作

当前实现是轻量规则，主要用于搭建架构。后续可以接入更细的意图安全分类。

### Tool Guardrail

位置：

```text
Planner 生成工具调用 → Tool Guardrail → ToolExecutor 执行工具
```

职责：

- 在工具真正执行前检查认证上下文
- 检查管理员工具是否只允许管理员调用
- 保留工具副作用、风险等级、输入字段等 metadata

这层和 RAG metadata filter 不是一回事：

- RAG metadata filter 控制“能召回哪些知识”
- Tool Guardrail 控制“当前 Agent 能不能调用这个工具”

后续 Day94 会继续补充租户、用户、角色、工具权限等级等更完整的越权拦截。

### Output Guardrail

位置：

```text
工具执行完成 → 生成最终回答 → Output Guardrail → 返回用户
```

职责：

- 拦截“绝对安全”“一定能飞”“无需审批”等过度承诺
- 防止 Agent 把未召回、未验证的内容说成确定政策
- 为 Day93 的最终回答约束和 Day97 的风险输出模板打基础

## 为什么不做成 Tool

Guardrail 不应该注册成普通 Tool。

原因：

- Tool 是 Agent 可以选择调用的能力
- Guardrail 是系统必须执行的边界
- 如果 Guardrail 是可选 Tool，Agent 可以因为规划错误而跳过它

因此当前实现把 Guardrail 放在 Agent Runtime 内部固定节点：

```text
InputGuardrail.check()
Planner / AgentLoop
ToolGuardrail.check()
ToolExecutor
OutputGuardrail.check()
Final Response
```

## 当前代码落点

- `app/agent/guardrail.py`：定义 Guardrail 数据结构、动作类型和轻量规则
- `app/agent/loop.py`：接入输入检查和最终输出检查
- `app/agent/executor.py`：接入工具调用前检查
- `tests/test_agent_guardrail.py`：覆盖输入拦截、工具前置权限、输出拦截和 Agent Loop 早停

## 后续扩展

- Day93：细化 Final Response Guardrail，控制无依据政策结论和高风险表达
- Day94：细化 Tool Guardrail，增加工具权限等级、租户隔离、用户隔离和角色校验
- Day96：把 Guardrail、RAG metadata filter、工具权限做成回归测试
- Day97：补充风险输出模板、拒答策略和保守说明
