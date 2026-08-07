# 多轮状态 Eval 测试指标设计

## 目标

Day108 的目标是验证 Agent 在多轮对话中是否正确保留、更新和隔离任务状态。

这类 Eval 不判断天气业务结果，而是判断：

- 上一轮状态是否被正确继承
- 用户本轮明确修改的字段是否覆盖旧值
- 缺字段追问后，用户补充信息是否能继续执行正确工具
- 意图切换后是否只携带合理上下文
- 不同 `user_id` 和 `session_id` 的状态是否互不污染
- 合并后的状态是否真的进入工具输入

## 测试入口

当前 `/agent/query` 在 `main.py` 中调用：

```python
orchestrate_task_query(payload.query, session_id=payload.session_id, user_id=current_user.id)
```

Day108 的评测脚本默认不直接调用真实工具，而是执行轻量链路：

```text
parse_natural_language_request
-> merge_agent_context
-> plan_next_step
-> update simulated session memory
-> compare expected state/tool input
```

这样可以避免真实天气接口、数据库和 RAG 造成不稳定。

## 数据集

数据集路径：

```text
evals/agent/multi_turn_cases.json
```

每个 case 是一个多轮对话：

```json
{
  "id": "multi_turn_modify_location_001",
  "category": "field_override",
  "user_id": "eval-user",
  "session_id": "day108-session-001",
  "turns": [
    {
      "input": "2026年8月8日深圳下午2点到5点适合巡检吗",
      "expected_intent": "evaluate",
      "expected_tool": "evaluate_flight_risk"
    },
    {
      "input": "地点改成广州，时间不变",
      "expected_modified_fields": ["location"],
      "expected_inherited_fields": ["date", "start_time", "end_time", "task_type"]
    }
  ]
}
```

## 核心指标

### 1. State Inheritance Accuracy

衡量应该继承的字段是否从上一轮状态保留下来。

```text
State Inheritance Accuracy = 正确继承字段数 / 应继承字段总数
```

例如用户说“时间不变”，应继承：

```text
date
start_time
end_time
task_type
```

### 2. State Override Accuracy

衡量用户明确修改的字段是否覆盖旧状态。

```text
State Override Accuracy = 正确覆盖字段数 / 应覆盖字段总数
```

例如“地点改成广州”：

```text
location: 深圳 -> 广州
```

### 3. Tool Input Consistency

衡量最终传入工具的参数是否等于期望状态。

```text
Tool Input Consistency = 匹配字段数 / 期望工具输入字段总数
```

这是 Day108 最重要的指标之一。状态合并正确但没有进入工具输入，仍然算失败。

### 4. Modified Fields Accuracy

衡量 `agent_runtime.context_merge.modified_fields` 是否准确。

```text
Modified Fields Accuracy = 正确标记修改字段数 / 期望修改字段总数
```

### 5. Invalidated Tools Accuracy

衡量字段变化后，是否标记需要重新运行的工具。

```text
Invalidated Tools Accuracy = 正确标记失效工具数 / 期望失效工具总数
```

例如修改 `location` 后，应重新运行：

```text
evaluate_flight_risk
query_knowledge_snippets
```

### 6. Clarification Continuation Pass Rate

衡量缺字段追问后，下一轮补齐字段是否能继续执行正确工具。

```text
Clarification Continuation Pass Rate = 补齐后成功执行样例数 / 追问补齐样例总数
```

典型场景：

```text
Turn 1: 明天下午能飞吗？
Turn 2: 深圳巡检
```

第二轮应继承第一轮的时间，并调用 `evaluate_flight_risk`。

### 7. Context Pollution Rate

衡量不该进入当前工具输入的历史字段是否被污染带入。

```text
Context Pollution Rate = 发生污染的轮次数 / 需要检查污染的轮次数
```

例如从风险评估切到政策查询时，不应把上一轮 `start_time`、`end_time` 塞进知识检索工具。

### 8. Session Isolation Pass Rate

衡量不同用户或不同 session 的上下文是否隔离。

```text
Session Isolation Pass Rate = 隔离检查通过轮次数 / 隔离检查总轮次数
```

## 单轮通过标准

单轮通过建议定义为：

```text
passed =
  intent_pass
  and tool_pass
  and expected_state_pass
  and tool_input_pass
  and modified_fields_pass
  and invalidated_tools_pass
  and no_context_pollution
```

## 运行命令

```powershell
.\.venv\Scripts\python.exe scripts/multi_turn_state_eval.py
```

输出：

```text
evals/reports/multi_turn_state_eval.json
evals/reports/multi_turn_state_eval.md
```

## Day108 验收标准

- 有一套可版本管理的多轮状态 Eval 数据集
- 一条命令可以生成多轮状态评测报告
- 报告能定位字段继承、覆盖、追问补全、污染和隔离问题
- 指标能解释 Agent 多轮状态质量，而不是只依赖人工体验
