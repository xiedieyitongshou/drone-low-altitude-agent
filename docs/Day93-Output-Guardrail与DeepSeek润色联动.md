# Day93 Output Guardrail 与 DeepSeek 润色联动

Day93 的目标是把最终回答约束从“简单文本拦截”推进到“LLM 润色前后都有边界检查”。

## 实现目标

- DeepSeek 只负责把结构化业务结果润色成自然语言
- Guardrail 负责判断内容是否可以交给 LLM 扩写，以及 LLM 输出是否可以返回用户
- 没有政策依据时，不让 LLM 放大政策、审批、禁飞、管制等结论
- LLM 输出不合规时，丢弃 LLM 文本，回退模板解释并追加保守边界说明

## 输出链路

```text
UnifiedBusinessResponse
  ↓
Pre-LLM Output Guardrail
  ↓
DeepSeek 润色 / 模板 fallback
  ↓
Post-LLM Output Guardrail
  ↓
response_composer 写回 explanation 与 guardrail metadata
```

## Pre-LLM Output Guardrail

位置：

- `app/agent/guardrail.py`
- `check_response_explanation_input_guardrail`

职责：

- 检查结构化响应中是否涉及政策、审批、许可、禁飞、管制、实名、合规等敏感语义
- 如果涉及上述内容，但 `details.knowledge_snippets` 为空，则不调用 DeepSeek
- 返回模板解释，并附加“不能替代官方审批”的边界说明

这样做的原因是：当前项目没有完备政策库，不能让 LLM 基于不完整依据扩写政策结论。

## Post-LLM Output Guardrail

位置：

- `app/agent/guardrail.py`
- `check_output_text_guardrail`

职责：

- 检查 DeepSeek 润色结果是否包含“绝对安全”“一定能飞”“无需审批”“保证通过”等过度承诺
- 如果命中，则丢弃 LLM 输出
- 回退模板解释，并附加保守边界说明

这保证了 DeepSeek 不能突破系统安全边界。

## 与 response_explainer 的联动

位置：

- `app/services/response_explainer.py`

处理顺序：

1. 先执行 Pre-LLM Output Guardrail
2. 通过后才调用 `generate_text`
3. LLM 返回后执行 Post-LLM Output Guardrail
4. 任一阶段不通过，都回退到模板解释
5. `ExplanationResult` 保存本次 Guardrail 检查结果

## 与 response_composer 的联动

位置：

- `app/services/response_composer.py`

当前会把解释结果写回：

- `response.explanation`
- `response.explanation_source`
- `response.llm_used`
- `response.details.explanation_guardrail`

其中 `explanation_guardrail` 用于后续前端展示、trace 扩展和 Eval 分析。

## 测试覆盖

测试文件：

- `tests/test_response_explainer_guardrail.py`

覆盖场景：

- 涉及政策但没有知识依据时，不调用 DeepSeek
- DeepSeek 输出过度承诺时，丢弃 LLM 文本并回退模板
- DeepSeek 输出合规时，保留 LLM 润色结果

运行命令：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_agent_guardrail.py tests/test_response_explainer_guardrail.py
```
