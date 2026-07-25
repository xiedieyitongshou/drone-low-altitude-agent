# Day 46：DeepSeek 自然语言解析接入方案

本文档固�?DeepSeek 解析层的设计契约。目标不是改变规则引擎，而是把用户自然语言稳定转换为现有业务接口可消费的结构化参数�?
## 1. 目标边界

DeepSeek 负责�?- 判断用户意图：`evaluate`、`recommend`、`compare`
- 抽取地点、日期、时间段、任务类型等任务参数
- 结合会话上下文补全省略表�?- 标记缺失字段，辅助后端返回补充提�?
DeepSeek 不负责：
- 判断是否适飞
- 修改风速、降水、预警等安全阈�?- 替代规则引擎输出 `allow`、`caution`、`reject`
- 直接调用天气 API 或数据库

后续主链路保持不变：

```text
自然语言输入
  -> DeepSeek 结构化解�?  -> Pydantic 校验
  -> Agent Orchestrator 分流
  -> evaluate / recommend / compare
  -> 规则引擎和业务服务输出结�?```

## 2. 当前规则解析输出结构

当前 `nl_parser.py` 输出 `ParsedTaskRequest`�?
```python
ParsedTaskRequest(
    intent="evaluate",
    target_endpoint="/cruise/evaluate",
    parsed={...},
    warnings=[],
    context_used=False,
    parser_source="rule",
)
```

DeepSeek 解析层最终也必须转换成同样结构，避免 `task_orchestrator.py` 和下游业务服务大改�?
## 3. LLM 原始输出 JSON Schema

DeepSeek 只允许返回一�?JSON object，不允许返回 Markdown、解释文本或代码块�?
允许字段�?
```json
{
  "intent": "evaluate",
  "location": "深圳�?,
  "locations": ["深圳�?, "南山�?],
  "date": "2026-07-26",
  "start_time": "14:00",
  "end_time": "17:00",
  "task_type": "cruise",
  "scan_hours": 72,
  "min_window_hours": 2,
  "top_k": 3,
  "comparison_mode": "default",
  "purpose": "用户原始问题",
  "missing_fields": [],
  "confidence": 0.92
}
```

字段约束�?- `intent` 只能�?`evaluate`、`recommend`、`compare`
- `task_type` 只能�?`cruise`、`inspection`、`hover`、`survey`
- `date` 必须�?`YYYY-MM-DD`
- `start_time` �?`end_time` 必须�?`HH:MM`，允�?`end_time=24:00`
- `locations` 至少包含 2 个地点时才能进入 `compare`
- `missing_fields` 只能包含后端认可的字段名
- `confidence` 仅用于日志和调试，不进入规则判断

## 4. 三类意图的必要字�?
### 4.1 单地点评�?evaluate

必要字段�?- `location`
- `date`
- `start_time`
- `end_time`
- `task_type`

转换后的 `parsed`�?
```json
{
  "location": "深圳�?,
  "date": "2026-07-26",
  "start_time": "14:00",
  "end_time": "17:00",
  "task_type": "cruise",
  "purpose": "深圳湾明天下�?点到5点可以飞�?
}
```

目标接口�?- `/cruise/evaluate`

### 4.2 推荐窗口 recommend

必要字段�?- `location`
- `date`
- `task_type`

默认字段�?- `scan_hours`: 72
- `min_window_hours`: 2

转换后的 `parsed`�?
```json
{
  "location": "深圳",
  "date": "2026-07-26",
  "task_type": "survey",
  "purpose": "深圳未来72小时最佳执行窗口是什么时�?,
  "scan_hours": 72,
  "min_window_hours": 2
}
```

目标接口�?- `/cruise/recommend`

说明�?- 如果用户只说“未�?72 小时”，但没有显式日期，默认使用当前日期�?- 如果用户说“明天开始未�?48 小时”，`date` 应解析为明天，`scan_hours` 应解析为 48�?
### 4.3 多地点比�?compare

必要字段�?- `locations`
- `date`
- `start_time`
- `end_time`
- `task_type`

默认字段�?- `top_k`: `min(3, len(locations))`
- `comparison_mode`: `default`

转换后的 `parsed`�?
```json
{
  "locations": ["深圳�?, "南山�?, "宝安机场附近"],
  "date": "2026-07-26",
  "start_time": "13:00",
  "end_time": "18:00",
  "task_type": "inspection",
  "purpose": "深圳湾、南山区、宝安机场附近明天下午哪个更适合先巡检",
  "top_k": 3,
  "comparison_mode": "default"
}
```

目标接口�?- `/cruise/compare`

## 5. 缺参策略

模型不能编造关键字段�?
如果缺少字段，DeepSeek 应返回：

```json
{
  "intent": "evaluate",
  "task_type": "cruise",
  "missing_fields": ["location", "start_time", "end_time"],
  "purpose": "帮我看看明天能不能飞"
}
```

后端处理原则�?- 如果会话上下文能补全，补全后继续执行
- 如果上下文也不能补全，抛�?`NaturalLanguageParseError`
- 错误响应中返回缺失字段，前端展示补充提示

建议缺参提示�?- 缺少 `location`：请补充任务地点
- 缺少 `date`：请补充任务日期
- 缺少 `start_time` / `end_time`：请补充任务时间�?- 缺少 `locations`：请提供至少两个候选地�?
## 6. 上下文继承规�?
输入�?DeepSeek 的上下文建议包含�?
```json
{
  "intent": "evaluate",
  "location": "深圳�?,
  "locations": ["深圳�?, "南山�?],
  "date": "2026-07-26",
  "start_time": "14:00",
  "end_time": "17:00",
  "task_type": "cruise",
  "scan_hours": 72
}
```

继承原则�?- 当前轮显式字段优�?- 当前轮缺失字段才使用上下�?- 用户明确表达“换成”“改为”“那后天”时，应覆盖上下文对应字�?- 如果当前轮意图不明确，可以参考上一�?`intent`
- 如果用户从单地点切换到多地点，以当前轮地点数量和比选表达优�?
示例�?
```text
上一轮：深圳湾明天下�?点到5点可以飞�?当前轮：那换成测绘呢
```

解析结果�?
```json
{
  "intent": "evaluate",
  "location": "深圳�?,
  "date": "2026-07-26",
  "start_time": "14:00",
  "end_time": "17:00",
  "task_type": "survey",
  "missing_fields": []
}
```

## 7. Parser Mode

建议支持三种模式�?
```env
NL_PARSER_MODE=rule
NL_PARSER_MODE=llm
NL_PARSER_MODE=hybrid
```

模式说明�?- `rule`：只使用当前 `nl_parser.py`
- `llm`：只使用 DeepSeek 解析，失败直接返回解析错�?- `hybrid`：优�?DeepSeek，失败后回退到规则解�?
推荐默认�?
```env
NL_PARSER_MODE=hybrid
```

原因�?- 面试演示时能展示 LLM 增强能力
- API 失败、余额不足、网络超时时仍有规则解析兜底
- 不影响项目离线可运行�?
## 8. 环境变量契约

当前项目已有统一 LLM 配置变量�?
```env
LLM_ENABLED=false
LLM_PROVIDER=none
LLM_MODEL=
LLM_BASE_URL=
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=20
LLM_MAX_TOKENS=600
```

DeepSeek 建议配置�?
```env
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_deepseek_api_key
LLM_TIMEOUT_SECONDS=20
LLM_MAX_TOKENS=600
NL_PARSER_MODE=hybrid
```

说明�?- 优先使用通用变量 `LLM_API_KEY`，便于后续兼容其�?OpenAI-compatible 服务
- 如需更直观，也可以在后续实现中兼�?`DEEPSEEK_API_KEY` 作为别名
- 真实 API Key 只能放在 `.env`，不能写�?Dockerfile、前端代码或 Git 仓库

## 9. Fallback 规则

以下情况触发 fallback�?- `LLM_ENABLED=false`
- `NL_PARSER_MODE=rule`
- DeepSeek 请求超时
- DeepSeek 返回空内�?- DeepSeek 返回�?JSON
- JSON 字段不符�?schema
- Pydantic 校验失败
- LLM 输出缺少必要字段且上下文无法补全

`hybrid` 模式�?fallback 后：
- `parser_source` 建议返回 `llm_fallback_rule`
- `warnings` 增加 fallback 原因，例�?`LLM 解析失败，已回退到规则解析`

`llm` 模式下不 fallback�?- 直接返回 `NaturalLanguageParseError`
- 便于开发阶段暴�?LLM prompt �?schema 问题

## 10. Day 46 完成标准

本日完成后，后续实现应满足：
- LLM 输出契约清晰
- 三类意图必要字段清晰
- 缺参策略清晰
- 上下文继承规则清�?- fallback 策略清晰
- 不改变规则引擎和核心业务接口

