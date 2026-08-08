# Day97 风险输出模板与快照测试

Day97 的目标是补强 Day93 的输出端能力：不仅判断最终回答能不能返回，还要让高风险、拒绝、降级场景稳定地“怎么说”。

## 实现原则

本项目不引入额外的大模型审核器。

原因：

- LLM 输出如果再交给 LLM 审核，本质上仍然把安全边界交给不稳定模型
- 当前项目的 LLM 使用点较少，主要是自然语言解析和结果润色
- 输出安全更适合用规则、模板和测试保证稳定性

当前方案：

```text
Prompt 约束
  ↓
固定风险输出模板
  ↓
关键词复检
  ↓
模板 fallback
  ↓
快照测试
```

## 模板策略

位置：

- `app/services/risk_output_templates.py`

输出统一拆成四段：

```text
当前结论
主要依据
边界说明
建议动作
```

当前覆盖模板：

- `prohibited`：禁飞 / 不建议执行
- `caution`：谨慎飞行
- `suitable`：风险较低但仍需复核
- `no_recommendation`：无推荐窗口
- `comparison`：多地点比选
- `history`：历史任务解释
- `unknown`：无法给出明确结论

## 关键词复检

位置：

- `find_unsafe_output_keywords`

当前拦截关键词：

- `绝对安全`
- `一定能飞`
- `无需审批`
- `不用审批`
- `保证通过`
- `肯定合法`
- `绕过审批`
- `不用报备`

这些词用于快照测试和 Post-LLM Output Guardrail，目标是防止最终输出出现过度承诺或审批误导。

## 与 DeepSeek 润色的关系

Day97 不新增 LLM-as-Judge。

DeepSeek 仍然只做表达润色，最终安全边界由以下机制控制：

- `EXPLAINER_SYSTEM_PROMPT` 限制 DeepSeek 不能新增事实、不能推翻规则结论
- Pre-LLM Output Guardrail 限制缺少政策依据的内容不交给 LLM 扩写
- Post-LLM Output Guardrail 拦截不合规 LLM 输出
- 模板 fallback 保证 LLM 不可用或不合规时仍有稳定输出
- 快照测试锁定高风险场景文案

## 当前代码落点

- `app/services/risk_output_templates.py`：风险输出模板和关键词检测
- `app/services/response_explainer.py`：模板 fallback 改为使用固定风险输出模板
- `tests/test_risk_output_templates.py`：快照式测试
- `tests/test_response_explainer_guardrail.py`：验证 LLM 输出不合规时回退模板

## 测试覆盖

测试内容：

- 禁飞输出必须包含“不建议执行”
- 谨慎飞行输出必须包含“谨慎执行”和复核建议
- 适飞输出不能表达为“绝对安全”
- 缺少推荐窗口时给出调整条件建议
- 推荐窗口输出必须强调候选方案和执行前复核
- 高风险关键词检测能命中禁止表达

运行命令：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_risk_output_templates.py tests/test_response_explainer_guardrail.py tests/test_agent_guardrail.py
```
