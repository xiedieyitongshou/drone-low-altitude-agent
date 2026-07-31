# Day 71：Tool Registry 设计

## 1. 当天目标

Day71 的目标不是马上重写业务代码，而是把当前固定 workflow 中已经存在的能力拆成 Agent 后续可以调用的工具，并为每个工具定义清晰边界。

核心目标：

- 梳理当前系统已有能力
- 明确哪些能力适合注册为工具
- 明确工具输入、输出、权限和副作用
- 为 Day72 的代码实现提供设计依据

当前项目的问题是：`/agent/query` 已经像一个自然语言入口，但后端执行方式仍然偏固定 workflow。用户输入后，系统主要按 `evaluate`、`recommend`、`compare` 三类意图进入固定分支。后续要升级为 Agent，需要先把业务能力拆成可组合的工具。

## 2. 当前能力梳理

| 能力 | 当前位置 | 说明 |
| --- | --- | --- |
| 自然语言解析 | `app/services/nl_parser.py`、`app/services/llm_task_parser.py` | 将用户自然语言解析为结构化任务参数 |
| 用户 Profile 补全 | `app/services/profile_memory.py` | 用用户长期偏好补全地点、任务类型、时间段等字段 |
| Session Memory | `app/services/session_memory.py` | 保存短期上下文，支持多轮任务继续 |
| 天气数据获取 | `app/services/weather/` | 调用外部天气服务获取天气和预警 |
| 单地点评估 | `app/services/cruise_evaluator.py` | 根据任务参数、天气和规则引擎输出风险判断 |
| 推荐窗口 | `app/services/recommendation_executor.py` | 扫描未来时间，推荐可执行窗口 |
| 多地点比选 | `app/services/comparison/` | 对多个地点进行评估并排序 |
| RAG 知识检索 | `app/services/advice_retriever.py`、`app/services/vector_knowledge_store.py` | 根据风险、地区、权限和时效检索建议与政策提示 |
| 历史持久化 | `app/services/history_persistence.py` | 保存结构化评估请求、天气快照和评估结果 |
| 历史查询 | `app/services/history_query.py`、`app/services/conversation_query.py` | 查询历史评估和自然语言会话记录 |
| 管理员审计 | `app/services/admin_conversation_audit.py`、`app/services/admin_stats.py` | 管理员跨用户查询任务与统计 |
| 响应组装 | `app/services/response_composer.py`、`app/services/response_explainer.py` | 将工具结果组织为统一业务响应和自然语言解释 |

## 3. Tool Registry 的设计原则

### 3.1 工具不是接口的简单搬运

Tool Registry 不是把所有 API endpoint 直接包装一遍，而是把 Agent 可能需要组合调用的业务能力抽象出来。

例如：

- `/cruise/evaluate` 是一个 HTTP 接口
- `evaluate_cruise_request_with_artifacts` 才是更适合作为工具的内部能力

原因是 Agent Runtime 应该复用服务层能力，而不是通过 HTTP 再调用自己。

### 3.2 工具必须声明副作用

Agent 不能像普通 workflow 一样默认执行所有步骤。每个工具必须说明它是否只读、是否只计算、是否写数据库、是否依赖外部服务。

建议使用以下副作用分类：

| 类型 | 含义 | 示例 |
| --- | --- | --- |
| `read_only` | 只读取已有数据，不改变系统状态 | 历史查询、Profile 查询、知识库检索 |
| `compute_only` | 只做本地计算，不落库 | 风险规则评估、推荐窗口计算、多地点比选排序 |
| `write` | 会改变数据库或用户状态 | 保存会话、保存评估历史、更新 Profile |
| `external_call` | 依赖外部服务，可能失败、超时或产生成本 | 天气查询、LLM 解析、后续 Embedding 调用 |

### 3.3 工具必须声明权限要求

每个工具需要说明调用时依赖什么身份信息：

- 是否需要登录用户
- 是否需要 `user_id`
- 是否需要 `tenant_id`
- 是否需要管理员角色
- 是否需要 RAG metadata 过滤

这一步是为了避免 Agent 后续在多用户场景下绕过权限边界。

### 3.4 工具必须输出结构化结果

工具输出不能只返回自然语言文本。后续 Agent Loop、Trace 和 Eval 都依赖结构化结果。

建议每个工具输出：

- `success`
- `tool_name`
- `data`
- `error_code`
- `message`
- `metadata`

## 4. ToolSpec 建议结构

Day72 可以围绕以下结构实现：

```python
class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    side_effect: Literal["read_only", "compute_only", "write", "external_call"]
    risk_level: Literal["low", "medium", "high"]
    requires_auth: bool = True
    requires_admin: bool = False
    timeout_ms: int = 30000
```

如果 Day72 先做最小实现，可以不强制绑定完整 Pydantic schema，但 `name`、`description`、`side_effect`、`risk_level`、`requires_auth` 应该先保留。

## 5. 第一批工具清单

### 5.1 自然语言解析工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `parse_task_intent` |
| 当前能力 | `parse_natural_language_request`、`parse_natural_language_request_with_llm` |
| 输入 | 用户 query、可选上下文 |
| 输出 | intent、target_endpoint、parsed、warnings、parser_source |
| 副作用 | `external_call` 或 `compute_only` |
| 风险等级 | `medium` |
| 权限 | 建议需要登录用户，因为解析结果会和用户上下文合并 |

说明：

- 规则解析是 `compute_only`
- LLM 解析是 `external_call`
- hybrid 模式下需要记录 fallback 来源

### 5.2 Profile 上下文查询工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `get_user_profile_context` |
| 当前能力 | `get_or_create_user_profile`、`merge_profile_context` |
| 输入 | `user_id` |
| 输出 | 默认地点、任务类型、时间段、输出偏好、常用地点 |
| 副作用 | `read_only` |
| 风险等级 | `low` |
| 权限 | 必须绑定当前登录用户 |

说明：

- 虽然当前实现中 `get_or_create_user_profile` 可能创建默认 Profile，但 Agent 语义上应尽量把查询和写入拆开
- 后续可以单独设计 `create_default_profile` 或 `update_user_profile` 写工具

### 5.3 Session 上下文查询工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `get_session_context` |
| 当前能力 | `session_memory_store.get` |
| 输入 | `user_id`、`session_id` |
| 输出 | 上一轮 intent、结构化参数、上下文摘要 |
| 副作用 | `read_only` |
| 风险等级 | `low` |
| 权限 | 必须按 `user_id + session_id` 隔离 |

说明：

- 该工具解决多轮追问和多轮修改的上下文读取问题
- 不能允许只靠 `session_id` 查询，必须绑定 `user_id`

### 5.4 天气查询工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `fetch_weather_context` |
| 当前能力 | `app/services/weather/`、`/cruise/weather-fetch` |
| 输入 | 地点、日期、时间段、任务类型 |
| 输出 | 地点解析结果、小时级天气、预警信息 |
| 副作用 | `external_call` |
| 风险等级 | `medium` |
| 权限 | 需要登录用户；不直接写业务数据 |

说明：

- 依赖外部天气服务，必须有超时、失败分类和 fallback
- 失败时不能让 Agent 编造天气结论

### 5.5 风险评估工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `evaluate_flight_risk` |
| 当前能力 | `evaluate_cruise_request_with_artifacts` |
| 输入 | `CruiseEvaluateRequest` |
| 输出 | 风险等级、小时级判断、风险原因、建议、天气快照 |
| 副作用 | `compute_only` |
| 风险等级 | `high` |
| 权限 | 需要登录用户；不直接落库 |

说明：

- 这个工具本身应该只负责计算
- 保存历史记录应拆成单独写工具，避免 Agent 每次评估都隐式写库
- 高风险原因必须来自规则引擎，不由 LLM 编造

### 5.6 保存评估历史工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `persist_flight_assessment` |
| 当前能力 | `persist_cruise_evaluation` |
| 输入 | 原始请求、评估 artifacts |
| 输出 | `request_id` |
| 副作用 | `write` |
| 风险等级 | `medium` |
| 权限 | 必须绑定当前用户 |

说明：

- 只有当业务需要保存结果时才调用
- 后续 Agent Planner 需要明确是否保存，而不是默认所有计算都落库

### 5.7 飞行窗口推荐工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `recommend_flight_windows` |
| 当前能力 | `build_recommendation_response` |
| 输入 | `RecommendationRequest` |
| 输出 | 推荐窗口、风险摘要、不可飞原因 |
| 副作用 | `compute_only` |
| 风险等级 | `high` |
| 权限 | 需要登录用户 |

说明：

- 推荐结果依赖天气和规则评估
- 如果缺少地点、日期、任务类型，应返回缺失字段，而不是强行推荐

### 5.8 多地点比选工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `compare_flight_locations` |
| 当前能力 | `compare_locations` |
| 输入 | `MultiLocationComparisonRequest` |
| 输出 | 多地点排序、推荐地点、各地点风险摘要 |
| 副作用 | `compute_only` |
| 风险等级 | `high` |
| 权限 | 需要登录用户 |

说明：

- 该工具适合处理“深圳湾和黄鹤楼哪个更适合飞”这类比选问题
- 后续可以只在用户意图为 `compare` 时调用，不再固定进入完整链路

### 5.9 RAG 知识检索工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `retrieve_rag_advice` |
| 当前能力 | `retrieve_knowledge_by_request`、`LocalVectorKnowledgeStore.retrieve` |
| 输入 | task_type、risk_reasons、warning_types、warning_levels、region、province、city、access_context |
| 输出 | snippets、advice、命中知识 metadata |
| 副作用 | `read_only` |
| 风险等级 | `medium` |
| 权限 | 必须执行 `visibility`、`tenant_id`、`user_id` 过滤 |

说明：

- 当前检索算法仍是 TF-IDF baseline
- Day67-Day70 已完成 metadata 数据治理
- 后续第 17 周升级为 BM25 + Embedding + Hybrid Retrieval
- RAG 结果不能覆盖规则引擎安全结论，只能作为依据和建议补充

### 5.10 历史查询工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `query_user_history` |
| 当前能力 | `get_cruise_history`、`list_user_conversations`、`get_user_conversation_detail` |
| 输入 | user_id、conversation_id、keyword、page、page_size |
| 输出 | 历史任务、会话摘要、详情 |
| 副作用 | `read_only` |
| 风险等级 | `low` |
| 权限 | 普通用户只能查询自己的数据 |

说明：

- 该工具解决“帮我查一下上次深圳湾任务”这类查询问题
- 不应触发天气、规则评估或推荐链路

### 5.11 会话保存工具

| 字段 | 设计 |
| --- | --- |
| 工具名 | `save_agent_conversation` |
| 当前能力 | `persist_conversation_record`、`session_memory_store.set` |
| 输入 | query、response、user_id、session_id、parsed |
| 输出 | conversation_id、session_id |
| 副作用 | `write` |
| 风险等级 | `medium` |
| 权限 | 必须绑定当前用户 |

说明：

- 这是典型写工具
- 后续 Agent Loop 需要明确在最终回答生成后调用，而不是在中间步骤随意调用

## 6. 工具副作用分层

### 6.1 只读工具

- `get_user_profile_context`
- `get_session_context`
- `retrieve_rag_advice`
- `query_user_history`

特点：

- 可以被 Planner 较安全地优先调用
- 必须遵守用户、租户和 metadata 权限过滤
- 适合查询、解释、追问上下文补全

### 6.2 纯计算工具

- `evaluate_flight_risk`
- `recommend_flight_windows`
- `compare_flight_locations`
- 规则解析模式下的 `parse_task_intent`

特点：

- 不直接改变数据库
- 但可能影响最终安全结论，所以风险等级较高
- 输出必须结构化，便于 trace 和 eval 校验

### 6.3 写入工具

- `persist_flight_assessment`
- `save_agent_conversation`
- 后续可能新增 `update_user_profile`

特点：

- 必须明确用户身份
- 不应由 Agent 在不确定场景下自动调用
- 后续可以增加确认机制或调用策略

### 6.4 外部依赖工具

- `fetch_weather_context`
- LLM 模式下的 `parse_task_intent`
- 后续 Embedding 生成工具

特点：

- 需要超时控制
- 需要错误分类
- 需要 fallback
- 需要在 trace 中记录耗时和失败原因

## 7. Day72 最小实现建议

Day72 不建议一次性改造所有业务链路。建议最小实现：

1. 新增 `app/agent/tools.py`
2. 定义 `ToolSpec`
3. 定义 `ToolRegistry`
4. 先注册以下 5 个工具：
   - `evaluate_flight_risk`
   - `recommend_flight_windows`
   - `compare_flight_locations`
   - `retrieve_rag_advice`
   - `query_user_history`
5. 写一个单元测试验证：
   - 工具可以注册
   - 工具可以按名称查询
   - 重复注册会报错
   - 不存在的工具会返回明确错误

Day72 的重点仍然不是 Agent Loop，而是让工具系统先成型。

## 8. 面试表达

可以这样解释 Day71：

> 我没有直接让 LLM 调用后端函数，而是先做 Tool Registry 设计。每个工具都声明名称、描述、输入输出、权限要求、风险等级和副作用类型。这样 Agent Planner 在选择工具前可以知道哪些工具只是查询，哪些工具会写数据库，哪些工具依赖外部服务，哪些工具涉及高风险安全判断。这个设计能避免 Agent 随意调用有副作用工具，也为后续 trace、eval 和 guardrail 打基础。

如果面试官追问“这和普通 service 有什么区别”，可以回答：

> 普通 service 是给业务代码调用的，默认调用方知道上下文；Agent tool 是给 Planner 调用的，必须自描述、可约束、可追踪、可评估。Tool Registry 的价值不是替代 service，而是在 Agent Runtime 上层建立统一调用协议。

## 9. Day71 完成标准

- 已梳理当前项目可工具化能力
- 已区分 `read_only`、`compute_only`、`write`、`external_call`
- 已明确第一批工具清单
- 已说明每个工具的权限要求和风险等级
- 已为 Day72 的 `ToolRegistry` 代码实现提供依据

