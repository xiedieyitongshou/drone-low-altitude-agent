# 无人机低空巡航任务决策系统

## 前后端本地启动

本项目现在包含 FastAPI 后端和 React 前端。本地开发时建议开两个终端分别启动。

### 1. 启动后端

在项目根目录执行：

```bash
cd D:\desktop\drone-low-altitude-agent
.\.venv\Scripts\activate
uvicorn main:app --reload
```

后端默认地址：

```text
http://localhost:8000
```

常用检查地址：

```text
http://localhost:8000/health
http://localhost:8000/docs
```

如果是第一次启动，先安装依赖并初始化数据库：

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 2. 启动前端

再打开一个新终端：

```bash
cd D:\desktop\drone-low-altitude-agent\frontend
npm install
npm run dev
```

前端默认地址通常是：

```text
http://localhost:5173
```

说明：

- `npm install` 只需要第一次安装依赖时执行
- 后续日常启动前端只需要执行 `npm run dev`
- 前端默认请求 `http://localhost:8000`
- 如需修改后端地址，在 `frontend/.env.local` 中配置 `VITE_API_BASE_URL`

示例：

```env
VITE_API_BASE_URL=http://localhost:8000
```

### 3. 启动顺序

推荐顺序：

```text
先启动后端 -> 再启动前端 -> 打开 http://localhost:5173
```

也可以只启动前端查看页面骨架，但涉及 `/health`、`/agent/query` 等接口的页面会提示后端连接失败。

## Docker Compose 完整启动

本项目也支持通过 Docker Compose 同时启动前端、后端和 Redis。

在项目根目录执行：

```bash
copy .env.docker.example .env
docker compose up -d --build --force-recreate
```

后台启动：

```bash
docker compose up -d --build --force-recreate
```

启动后访问：

```text
前端展示页面：http://localhost:5173
后端 OpenAPI：http://localhost:8000/docs
后端健康检查：http://localhost:8000/health
```

当前 Compose 服务包括：

- `frontend`：React 前端，Nginx 托管静态资源
- `app`：FastAPI 后端，启动时自动执行 Alembic 迁移，支持 JWT、多用户记忆、管理员接口和核心单元测试
- `redis`：会话上下文缓存

前端 Docker 构建时默认注入：

```env
VITE_API_BASE_URL=http://localhost:8000
```

因此浏览器打开 `http://localhost:5173` 后，会直接请求本机映射出来的后端 API。

### Docker 下初始化管理员

普通注册接口只能创建 `user` 角色。Docker 演示如果需要管理员后台，先在 `.env` 中配置：

```env
JWT_SECRET_KEY=replace-with-random-secret
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=change-me-before-deploy
```

第一次创建管理员时，显式执行一次初始化服务：

```bash
docker compose --profile tools run --rm admin-init
```

该命令会先执行数据库迁移，再创建或激活 `.env` 中指定的初始管理员。后续正常启动项目：

```bash
docker compose up -d --build --force-recreate
```

后续管理员只能由已有管理员在管理页面或 `/admin/users/{user_id}/role` 接口授权产生。`admin-init` 是一次性工具服务，不会随普通 `docker compose up` 自动执行。

说明：

- `INITIAL_ADMIN_PASSWORD` 示例值只用于本地演示，正式使用前必须改成自己的强密码。
- 如果按本文档示例创建，本地管理员账号为 `admin`，密码为 `.env` 中的 `INITIAL_ADMIN_PASSWORD`。
- 不要把真实管理员密码提交到 GitHub。

### Docker 内验证

如需在 Docker 后端容器内验证测试，可执行：

```bash
docker compose exec app python -m pytest
```

这是一个从“阿里云百炼工作流原型”重构出来的本地后端项目。原型阶段主要依赖工作流节点完成天气查询和条件判断；重构后，项目改为基于 FastAPI 的模块化后端服务，把天气数据获取、数据标准化、规则判断、推荐、比选、历史记录、自然语言入口和知识库建议拆成可维护的 Python 模块。

项目目标不是简单查询天气，而是面向无人机低空任务，回答这类问题：

- 当前地点和时间段是否适合飞行？
- 未来什么时候更适合执行任务？
- 多个地点中哪个地点优先级更高？
- 风险原因是什么？有什么操作建议？
- 用户连续追问时，能否复用上一轮上下文？
- 不同登录用户之间的历史、会话和长期偏好能否安全隔离？

## 当前功能

- 天气服务：接入和风天气，支持地点解析、逐小时天气、天气预警获取。
- 数据标准化：通过 mapper 层把外部 API 数据转换为内部统一结构。
- 规则引擎：根据任务类型、天气指标和预警信息输出逐小时风险判断。
- 推荐窗口：线性扫描逐小时评估结果，按禁飞小时和时间断点切分连续可执行窗口，避免重复推荐重叠时间段。
- 多地点比选：支持多个地点并行评估，并按可飞小时、连续窗口、风险质量等维度排序。
- 历史记录：使用 SQLite + SQLAlchemy 保存评估请求、天气快照、预警和判断结果。
- 自然语言入口：支持基于关键词/正则和 DeepSeek 结构化输出的任务信息解析，可通过 `NL_PARSER_MODE=rule|llm|hybrid` 控制解析策略。
- 多用户认证：支持用户注册、登录、JWT 鉴权和 `/auth/me` 当前用户识别。
- 编排器：通过 `/agent/query` 串起解析、天气、规则、推荐、比选、响应生成，并使用 token 用户作为真实数据归属。
- Agent Runtime 基础：已新增 Tool Registry、AgentState、规则 Planner 和最小 AgentLoop，可通过 `AGENT_RUNTIME_MODE=legacy|loop` 灰度切换；默认保留 legacy workflow，loop 模式失败时可回退旧编排链路。
- Agent 错误恢复：已引入工具失败分类、恢复策略和兜底输出，支持参数缺失追问、空结果提示、工具异常转 legacy fallback、权限错误直接拒绝等路径。
- Agent Trace 闭环：已记录 plan、tool_call、tool_result、error、fallback、final_response 等事件，并支持按当前登录用户查询自己的执行链路。
- 会话记忆：支持 `ttlcache`、`redis`、`database` 三种后端，按 `user_id + session_id` 隔离短期上下文。
- Profile Memory：绑定真实用户，支持查看和编辑默认地点、任务类型、时间段、输出偏好和常用列表。
- Conversation History：`/agent/query` 调用后自动保存自然语言请求、解析结果、响应摘要和完整响应，并支持按当前用户隔离查询和关键词检索。
- RAG 建议原型：基于本地知识库 JSON 和 TF-IDF baseline 检索风险说明与操作建议；知识条目已支持类型、地域、权限、租户、用户、版本、时效和审核状态等 metadata。
- RAG 数据治理：检索前按 `visibility`、`tenant_id`、`user_id` 做用户隔离，按 `region`、`province`、`city`、`task_type`、`risk_tags`、`effective_at`、`expires_at`、`review_status` 做业务过滤，避免不同用户、不同地区、过期知识互相污染。
- LLM 增强：已引入统一 LLM 客户端，复用于自然语言任务解析和最终结果解释；大模型只负责理解输入和润色表达，不替代规则引擎做安全判断。

## 系统结构

```text
用户输入
  ↓
JWT 鉴权 / 当前用户识别
  ↓
自然语言解析 / 结构化请求
  ↓
LLM 结构化解析 / 规则解析 fallback
  ↓
Orchestrator 编排器
  ↓
Agent Runtime 开关：legacy workflow / loop runtime
  ↓
Tool Registry / AgentState / Rule Planner / AgentLoop
  ↓
ToolExecutor / FailurePolicy / TraceEvent
  ↓
Weather Provider 获取原始天气数据
  ↓
Mapper 转换为内部统一模型
  ↓
规则引擎 / 推荐模块 / 多地点比选
  ↓
历史落库 / RAG metadata 过滤与建议检索
  ↓
Session Memory / Profile Memory 按用户隔离
  ↓
LLM 结果解释 / 模板解释 fallback
  ↓
统一响应输出
```

核心设计思路：

- Provider 层只负责对接外部 API。
- Mapper 层负责屏蔽不同数据源格式差异。
- Rules 层只依赖内部统一数据结构，不直接依赖和风天气原始字段。
- Service / Orchestrator 负责组织流程，不把规则细节写死在接口中；Agent Runtime 通过工具注册、状态管理、规则规划和循环执行逐步替代固定 workflow。
- Trace / Logging 层记录 Agent 状态转换、工具调用、错误分类和兜底路径，用于解释单次请求的执行过程。
- Auth / Memory 层只负责身份识别、数据归属和上下文补全，不参与飞行安全判断。
- RAG 层先完成企业知识库常见的数据治理，再升级为 BM25 + Embedding + Hybrid Retrieval 的可评估检索工具。

## 主要接口

启动服务后可访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档。

- `GET /health`：健康检查。
- `POST /auth/register`：注册普通用户。
- `POST /auth/login`：登录并返回 JWT access token。
- `GET /auth/me`：获取当前登录用户信息。
- `GET /users/me/profile`：查看当前用户长期偏好。
- `PATCH /users/me/profile`：编辑当前用户长期偏好。
- `GET /admin/users`：管理员查询用户列表，支持用户名、角色、启用状态筛选。
- `PATCH /admin/users/{user_id}/status`：管理员启用或禁用用户。
- `PATCH /admin/users/{user_id}/role`：管理员在 `user` 与 `admin` 之间调整用户角色。
- `GET /admin/stats/tasks`：管理员查看用户、任务、失败、风险和解析失败统计。
- `GET /admin/conversations`：管理员跨用户查询任务会话历史，支持用户、会话、意图、解析来源、成功状态、关键词和时间范围筛选。
- `GET /admin/conversations/{conversation_id}`：管理员查看单条任务会话完整详情。
- `POST /nl/parse`：自然语言任务解析。
- `POST /agent/query`：Agent 主入口，支持一句话完成任务调用；需要 `Authorization: Bearer <token>`。
- `GET /agent/conversations`：查询当前用户对话历史，支持分页、关键词、会话、意图和解析来源筛选。
- `GET /agent/conversations/{conversation_id}`：查询当前用户单条对话详情；前端通常通过历史列表点击进入。
- `GET /agent/traces/{trace_id}`：查询当前用户自己的 Agent trace，查看状态转换、工具调用、错误分类和兜底路径。
- `POST /cruise/weather-fetch`：获取地点、天气和预警原始数据。
- `POST /cruise/evaluate`：单地点、指定时间段巡航风险评估。
- `POST /cruise/recommend`：推荐未来合适执行窗口。
- `POST /cruise/compare`：多地点任务风险比选。
- `GET /cruise/history/{request_id}`：查询历史评估记录。
- `GET /cruise/history/{request_id}/composed`：查询统一业务响应格式的历史记录。
- `POST /knowledge/advice/retrieve`：根据风险结果检索知识库建议。

## 技术栈

- Web 框架：FastAPI、Uvicorn
- 数据校验：Pydantic
- HTTP 请求：httpx
- 配置管理：python-dotenv
- 数据库：SQLite、SQLAlchemy、Alembic
- 认证鉴权：bcrypt、PyJWT、FastAPI HTTPBearer
- 会话缓存/持久化：cachetools TTLCache、Redis、Database backend
- 记忆持久化：users、user_profiles、conversation_records、session_records
- Agent Runtime：Tool Registry、AgentState、Rule Planner、AgentLoop、ToolExecutor、FailurePolicy、TraceEvent、legacy fallback
- 知识检索：当前为 scikit-learn TF-IDF + cosine similarity baseline；已完成 metadata 过滤，计划升级为 BM25 + Embedding + Hybrid Retrieval

当前 RAG 检索是可运行的轻量版本。项目后续不会只停留在 TF-IDF，而是会把 RAG 做成 Agent 可调用的企业级知识工具：BM25 解决政策名、地名、编号等关键词精确召回；Embedding 解决口语化提问和知识库措辞不一致的语义召回；Hybrid Retrieval 通过融合排序、metadata boost、chunk 策略、rerank 和 RAG Eval 提升可解释性与可验证性。

## 本地运行

### 1. 安装依赖

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，并填写自己的和风天气配置。

常用配置项包括：

```env
QWEATHER_API_KEY=你的和风天气Key
QWEATHER_GEO_BASE_URL=https://你的专属host
QWEATHER_WEATHER_BASE_URL=https://你的专属host
QWEATHER_WARNING_BASE_URL=https://你的专属host
DATABASE_URL=sqlite:///./data/drone_agent.db
JWT_SECRET_KEY=请替换为随机密钥
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
SESSION_MEMORY_BACKEND=ttlcache
REDIS_URL=redis://localhost:6379/0
AGENT_RUNTIME_MODE=legacy
```

`.env` 不应提交到 GitHub。

### Agent Runtime 配置

当前 `/agent/query` 支持两种运行模式：

```env
AGENT_RUNTIME_MODE=legacy
```

默认模式，继续使用原有固定 workflow，适合稳定演示和线上兼容。

```env
AGENT_RUNTIME_MODE=loop
```

实验模式，启用 Day71-Day76 实现的 Agent Runtime：

- `Tool Registry`：统一注册风险评估、飞行窗口推荐、多地点比选、RAG 检索、历史查询等工具。
- `AgentState`：保存当前意图、任务草稿、已确认字段、缺失字段、工具结果、错误和 step 历史。
- `Rule Planner`：根据状态决定下一步是追问、调用工具、直接回答还是 fallback。
- `AgentLoop`：执行 Planner 产出的计划，将工具结果写回状态，并通过最大轮次限制避免无限循环。
- `legacy fallback`：loop 模式失败时可回退原始编排链路，保证现有接口兼容。

响应中会额外返回可选 `agent_runtime` 字段，用于查看 `trace_id`、`run_id`、状态、计划动作和工具结果。该字段是调试增强，不影响旧前端使用原有字段。

### Session Memory 配置

本地默认使用进程内缓存：

```env
SESSION_MEMORY_BACKEND=ttlcache
SESSION_MEMORY_TTL_SECONDS=1800
SESSION_MEMORY_MAXSIZE=1024
```

如果 Docker 或服务器环境中启动了 Redis，可以切换为：

```env
SESSION_MEMORY_BACKEND=redis
REDIS_URL=redis://redis:6379/0
SESSION_MEMORY_REDIS_KEY_PREFIX=drone_agent:session:
```

注意：`redis://redis:6379/0` 中的 `redis` 是 `docker-compose.yml` 里的 Redis 服务名；如果在本机直接连接 Redis，通常使用 `redis://localhost:6379/0`。

如果希望刷新页面或重启进程后仍能恢复会话上下文，可以切换为数据库持久化：

```env
SESSION_MEMORY_BACKEND=database
SESSION_MEMORY_TTL_SECONDS=1800
```

无论使用 `ttlcache`、`redis` 还是 `database`，Session Memory 都按 `user_id + session_id` 隔离，避免不同用户使用相同 `session_id` 时互相污染。

### 3. 初始化数据库

```bash
.\.venv\Scripts\python.exe -m alembic upgrade head
```

### 4. 启动服务

```bash
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

访问：

```text
http://127.0.0.1:8000/docs
```

### 5. 运行关键测试

多用户、认证、对话历史、Session Memory 和 Profile Memory 相关测试：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_auth_service.py tests/test_auth_api.py tests/test_agent_auth_binding.py tests/test_conversation_history_api.py tests/test_session_memory.py tests/test_user_profile_api.py
```

Agent Runtime、Tool Registry、状态机、Planner、Loop 和灰度接入相关测试：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry.py tests/test_agent_state.py tests/test_agent_planner.py tests/test_agent_loop.py tests/test_task_orchestrator_agent_runtime.py
```

Agent trace、日志、工具失败恢复和兜底输出相关测试：

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_agent_trace.py tests/test_agent_trace_api.py tests/test_agent_logging.py tests/test_tool_executor.py tests/test_failure_policy.py tests/test_agent_fallback.py
```

检查 Alembic 模型和迁移是否一致：

```bash
.\.venv\Scripts\python.exe -m alembic check
```

### 6. 使用 DBeaver 查看数据库

当前本地默认数据库文件：

```text
data/drone_agent.db
```

可以用 DBeaver 建立 SQLite 连接查看这些表：

- `users`
- `user_profiles`
- `conversation_records`
- `session_records`
- `agent_trace_events`

DBeaver 只用于数据查看、调试和人工核查；正式表结构变更仍通过 `SQLAlchemy + Alembic migration` 完成。

## 示例请求

### 单地点评估

```json
{
  "location": "Shenzhen",
  "date": "2026-07-14",
  "start_time": "09:00",
  "end_time": "12:00",
  "task_type": "cruise",
  "purpose": "日常巡航任务"
}
```

### 推荐执行窗口

```json
{
  "location": "Shenzhen",
  "date": "2026-07-14",
  "task_type": "cruise",
  "purpose": "日常巡航任务",
  "scan_hours": 72,
  "min_window_hours": 2
}
```

### Agent 自然语言入口

先登录获取 token：

```json
{
  "username": "demo",
  "password": "demo123456"
}
```

请求：

```text
POST /auth/login
```

后续调用 `/agent/query` 时在请求头携带：

```text
Authorization: Bearer <access_token>
```

```json
{
  "query": "帮我看一下深圳明天下午适不适合做无人机巡航",
  "session_id": "demo-session"
}
```

`/agent/query` 不再信任请求体中的 `user_id`，业务数据归属以后端 token 解析出的当前用户为准。

### 用户 Profile 示例

```json
{
  "default_location": "深圳湾",
  "default_task_type": "inspection",
  "default_start_time": "14:00",
  "default_end_time": "17:00",
  "output_style": "detailed",
  "common_locations": ["深圳湾", "南山区"],
  "common_task_types": ["inspection", "survey"]
}
```

请求：

```text
PATCH /users/me/profile
Authorization: Bearer <access_token>
```

当用户后续输入“明天适合飞吗”这类缺少地点、任务类型和时间段的表达时，系统可以从当前用户 Profile 中补全默认地点、任务类型和时间段。

### 对话历史检索示例

```text
GET /agent/conversations?keyword=深圳&page=1&page_size=20
Authorization: Bearer <access_token>
```

说明：

- 前端用户通过关键词和历史列表检索内容。
- 后端继续使用 `conversation_id` 定位单条详情。
- 普通用户只能查询自己的对话历史，即使知道其他用户的 `conversation_id` 也会返回 `404`。

### 管理员用户管理示例

普通注册接口只能创建 `user` 角色。第一个管理员建议由开发期初始化脚本创建：

```bash
.\.venv\Scripts\python.exe scripts\create_initial_admin.py
```

脚本读取 `.env` 中的 `INITIAL_ADMIN_USERNAME` 和 `INITIAL_ADMIN_PASSWORD`。后续管理员只能由已有管理员通过后台接口授权产生。

Docker 环境可以执行：

```bash
docker compose --profile tools run --rm admin-init
```

```text
GET /admin/users?role=user&is_active=true
Authorization: Bearer <admin_access_token>
```

权限边界：

- 普通用户访问 `/admin/*` 返回 `403`。
- 不能禁用最后一个可用管理员。
- 不能将最后一个可用管理员降级为普通用户。

### 管理员任务审计示例

管理员可以跨用户查看任务运行记录，但接口只提供查询能力，不修改历史任务内容。

```text
GET /admin/conversations?user_id=<user_id>&intent=evaluate&success=true&page=1&page_size=20
Authorization: Bearer <admin_access_token>
```

```text
GET /admin/conversations/<conversation_id>
Authorization: Bearer <admin_access_token>
```

## 当前阶段

项目已经完成从基础天气判断工具到任务决策系统的主体升级：

- 第一阶段：后端服务、天气服务、Schema、输入校验、数据 mapper。
- 第二阶段：时间提取、预警提取、规则引擎、任务阈值配置、评估接口。
- 第三阶段：推荐窗口、多地点比选、历史持久化、多任务模板。
- 第四阶段：自然语言解析、Agent 编排、会话记忆、统一响应。
- 第五阶段：已接入轻量 RAG 建议检索、Profile Memory 和 Conversation History。
- 第六阶段：已接入 DeepSeek 结构化自然语言解析，保留规则解析作为 fallback；已引入统一 LLM 客户端，用于任务解析和最终结果解释。
- 第七阶段：已接入前端登录注册、请求鉴权、用户历史检索和 Profile 设置页。
- 第八阶段：已接入多用户登录、JWT 鉴权、用户数据隔离、Session Memory 持久化和用户 Profile 管理。
- 第九阶段：已接入管理员统计、用户管理、全局任务审计和 Docker 初始化管理员流程。
- 第十阶段：已完成 RAG 知识库 metadata 数据治理，支持知识类型、地域、可见性、租户、用户、版本、有效期和审核状态过滤。
- 第十一阶段：已完成 Agent Runtime 基础改造，包含 Tool Registry、AgentState、规则 Planner、最小 AgentLoop、`AGENT_RUNTIME_MODE` 灰度接入和完整回归测试。
- 第十二阶段：已完成 Agent Trace、结构化日志、工具失败分类、恢复策略、兜底输出和用户级 trace 查询闭环。

## 后续计划

- 第 14 周：混合型业务编排，同一自然语言入口支持查询、评估、推荐、比选、追问和多轮修改。
- 第 15 周：Agent Eval 与 Tool Calling 质量评估，用样例集评估意图识别、工具选择、多轮状态和失败恢复。
- 第 16 周：Guardrail、安全边界与 Agent 输出约束，限制越权调用、无依据政策结论和高风险过度承诺。
- 第 17 周：Hybrid RAG 检索增强，在 Day70 数据治理基础上补齐 BM25、Embedding、Hybrid Retrieval、chunk 策略、rerank、query rewrite、低置信 fallback 和 RAG Eval。
- 第 18 周：CI/CD、README、面试指南和端到端演示收尾，形成可运行、可解释、可评估、可展示的求职版本。
