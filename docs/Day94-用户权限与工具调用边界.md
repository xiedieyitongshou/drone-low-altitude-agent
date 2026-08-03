# Day94 用户权限与工具调用边界

Day94 的目标是把工具分类和用户上下文真正接入 Tool Guardrail，防止 Agent 在动态调用工具时绕过权限边界。

## 核心定位

Day94 不是重新做数据治理，而是应用前面已经完成的数据治理。

```text
Day67-Day70：数据层隔离
Day92：Tool Guardrail 检查点
Day94：工具调用前权限边界
```

可以概括为：

```text
数据上有标签，工具调用时必须尊重这些标签。
```

## 与 RAG 数据治理的关系

RAG 数据治理解决的是“用户能看到哪些知识”：

- `visibility`
- `user_id`
- `tenant_id`
- `region`
- `province`
- `city`
- `effective_at`
- `expires_at`
- `review_status`

Tool Guardrail 解决的是“当前用户能不能调用这个工具”：

- 未登录用户不能调用需要登录的工具
- 普通用户不能调用管理员工具
- 当前用户不能通过 payload 伪造其他 `user_id`
- RAG 和历史查询必须以 `ToolExecutionContext.user_id` 作为唯一可信用户来源

当前项目是个人求职项目，所以主线强调“用户隔离”。`tenant_id` 保留为企业 RAG 扩展字段，不作为当前系统的主要边界。

## 工具权限模型

当前 `ToolSpec` 已具备基础分类：

- `side_effect`：`read_only`、`compute_only`、`write`、`external_call`
- `risk_level`：`low`、`medium`、`high`
- `requires_auth`：是否需要登录用户
- `requires_admin`：是否需要管理员
- `allowed_roles`：允许调用的角色集合
- `user_scope`：工具作用域，当前支持 `public`、`current_user`、`admin`

其中：

- `public`：公共工具，不绑定用户私有数据
- `current_user`：只能访问当前登录用户自己的数据
- `admin`：管理员级工具

## Tool Guardrail 检查顺序

工具执行前会经过统一检查：

```text
Planner 生成工具调用
  ↓
ToolExecutor
  ↓
Tool Guardrail
  ↓
检查登录上下文
  ↓
检查管理员权限
  ↓
检查 allowed_roles
  ↓
检查 payload user_id 是否伪造
  ↓
允许执行 / 拒绝并写入 trace
```

## 当前实现

代码位置：

- `app/agent/tools.py`：扩展 `ToolSpec`，增加 `allowed_roles` 和 `user_scope`
- `app/agent/guardrail.py`：强化 `check_tool_guardrail`
- `app/agent/executor.py`：工具执行前统一调用 Tool Guardrail，并把拒绝写入日志和 trace
- `app/agent/failure_policy.py`：把工具权限错误归类为 `permission_denied`

新增错误码：

- `TOOL_PERMISSION_DENIED`：当前角色不允许调用工具
- `TOOL_USER_SCOPE_VIOLATION`：payload 中的 `user_id` 与当前登录用户不一致

## 安全边界

当前可信用户来源只有：

```text
ToolExecutionContext.user_id
```

工具 payload 中的 `user_id` 不能作为可信身份。对于 `current_user` 工具，如果 payload 中传入了其他用户的 `user_id`，会在执行前被拒绝，handler 不会运行。

这可以防止以下问题：

- 用户请求中伪造 `user_id`
- Agent 根据错误输入调用了不该访问的数据
- 查询历史、私有知识等 current-user 工具被跨用户访问
- 普通用户调用管理员工具

## 测试覆盖

测试文件：

- `tests/test_agent_guardrail.py`

覆盖场景：

- 未登录用户调用需要登录工具被拒绝
- 普通用户调用管理员作用域工具被拒绝
- payload 伪造其他 `user_id` 被拒绝
- ToolExecutor 在 handler 执行前完成拦截

运行命令：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_agent_guardrail.py tests/test_agent_loop.py tests/test_tool_registry.py
```

## 面试解释口径

权限隔离分两层实现：

1. 数据层：通过 metadata 标记知识和记录的归属、可见性、地域和有效期。
2. 工具层：通过 Tool Guardrail 在 Agent 调用工具前检查当前用户、角色和工具作用域。

这样即使 Agent 是动态规划和调用工具，也不能绕过底层数据隔离和当前登录用户边界。
