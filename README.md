# 低空作业气象决策 Agent

一个面向无人机低空作业场景的气象决策 Agent 项目。系统接入天气数据，结合任务类型、逐小时天气、预警信息和业务规则，判断指定地点和时间段是否适合执行低空巡航、测绘、巡检等任务，并提供推荐执行窗口、多地点比选、历史复盘、RAG 操作建议、多轮上下文和管理员审计能力。

项目核心原则是将业务安全判断与 AI 增强能力解耦：LLM、RAG 和 Memory 负责理解、补全、解释和检索增强，最终适飞 / 慎飞 / 禁飞结论由确定性规则引擎给出，保证结果可复现、可测试、可追踪。

## 项目状态

当前版本支持本地运行和 Docker Compose 联调。默认配置使用规则解析、SQLite 和 TTLCache；Docker 环境可切换到 Redis 会话记忆。LLM 解析默认关闭，需要配置 API Key 后通过 `NL_PARSER_MODE=hybrid` 启用。

## 项目亮点

- 业务闭环：支持单地点评估、推荐窗口、多地点比选、历史复盘和自然语言统一入口。
- Agent Runtime：通过 Business Route、Planner、Tool Registry、Tool Executor 和 Agent State 组织工具调用，而不是固定串行 workflow。
- 安全边界：LLM 不直接判断飞行安全，RAG 不覆盖规则结论，Guardrail 固定在输入、工具调用和最终输出阶段。
- 可解释 Trace：记录 plan、tool_call、tool_result、error、fallback、final_response 等事件，支持按用户查询执行链路。
- 多轮上下文：支持 pending task、字段继承、字段覆盖、会话隔离和 Profile Memory 补全。
- 多用户体系：支持注册、登录、JWT 鉴权、普通用户数据隔离、管理员用户治理和会话审计。
- RAG 数据治理：支持知识类型、地域、租户、用户、可见性、时效、审核状态等 metadata 过滤。
- Eval 体系：包含 Tool Calling Eval、Multi-turn State Eval、Failure Recovery Eval 和 RAG Eval，用样例集量化 Agent 行为。
- 前后端控制台：React + Vite 页面覆盖 Agent 对话、评估、推荐、比选、历史、Profile 和管理员功能。
- Docker 化：提供后端、前端和 Redis 的 Docker Compose 联调环境，便于本地运行和服务器部署前验证。

## 系统架构

```text
Browser / React Console
  -> Auth / Axios Client
  -> FastAPI API Layer
      -> Auth Dependency / User Scope
      -> Agent Orchestrator
          -> NL Parser: rule / llm / hybrid
          -> Context Manager: session + profile + pending task
          -> Business Route / Planner
          -> Tool Registry / Tool Executor
          -> Guardrail / Failure Policy / Trace
      -> Business Services
          -> Weather Provider / Mapper
          -> Rule Engine
          -> Recommendation Engine
          -> Location Comparison
          -> Conversation History
          -> RAG Retriever
      -> Storage
          -> SQLite / SQLAlchemy / Alembic
          -> Redis Session Memory
```

核心原则：业务安全判断沉淀在规则层，Agent 只负责编排业务服务。自然语言、LLM、RAG、记忆和前端控制台都可以增强交互体验，但不会覆盖最终安全结论。

## 核心能力

### 1. 低空作业风险评估

输入地点、日期、时间段和任务类型后，系统会获取逐小时天气和天气预警，并按规则输出整体结论和逐小时风险因素。

典型输入：

```text
深圳湾明天下午 2 点到 5 点适合做低空巡航吗？
```

输出重点：

- 整体结论：适飞 / 慎飞 / 禁飞
- 判断原因：风速、风力、降水、能见度、天气预警等风险因素
- 小时级结果：每个小时的风险等级和命中的规则
- 操作建议：来自规则解释和 RAG 检索的保守建议

### 2. 推荐执行窗口

系统可以扫描未来一段时间，找出连续低风险时间窗口，辅助任务调度。

典型输入：

```text
深圳未来 72 小时哪个时间段更适合巡检？
```

排序考虑：

- 可飞小时数
- 风险等级
- 连续性
- 任务类型要求
- 预警影响

### 3. 多地点比选

系统支持对多个候选地点进行统一评估，并输出推荐地点和排序原因。

典型输入：

```text
深圳湾、南山区、宝安机场附近明天下午哪个更适合先巡检？
```

输出重点：

- 推荐地点
- 综合排序
- 各地点可飞小时数
- 最长连续可飞窗口
- 主要风险差异

### 4. 自然语言 Agent 入口

`/agent/query` 是统一自然语言入口，负责把用户输入转换为业务任务，并调用必要工具完成结果生成。

支持能力：

- 单地点评估
- 推荐窗口
- 多地点比选
- 历史查询
- 知识检索
- 多轮追问
- 任务条件修改
- 工具失败恢复

多轮示例：

```text
用户：帮我看看深圳湾明天下午适不适合巡航
系统：解析地点、时间段和任务类型，调用天气与规则工具，返回评估结论

用户：那换成后天上午呢
系统：继承上一轮地点和任务类型，只覆盖日期和时间段，重新评估
```

### 5. RAG 操作建议增强

RAG 不负责改变适飞结论，只根据业务结果、风险标签、地区和权限过滤知识库，补充操作建议、SOP 提示和政策边界说明。

当前支持：

- TF-IDF baseline
- BM25 关键词召回
- Embedding 语义召回
- Hybrid Retrieval
- chunk 策略
- metadata filter
- rerank
- query rewrite
- 低置信 fallback

重要边界：如果知识库空召回或低置信，系统应返回保守说明，而不是编造政策依据。

### 6. Trace、Guardrail 与失败恢复

Agent 执行过程中会记录结构化 trace，便于解释一次请求为什么调用某个工具、在哪里失败、如何 fallback。

覆盖场景：

- 参数缺失：追问用户，不直接生成安全结论
- 外部依赖失败：返回可解释错误，不编造天气数据
- 权限不足：拒绝访问，不能通过 fallback 绕过权限
- RAG 空召回：返回保守提示
- LLM 失败：回退规则解析或固定模板输出

### 7. 多用户、权限和审计

项目支持真实登录用户，不再依赖固定 `default_user`。

权限模型：

- 普通用户只能访问自己的历史、会话、Profile 和 trace
- 管理员可以查看用户列表、系统统计和全局会话审计
- `/agent/query` 不信任前端传入的 `user_id`，以后端 token 解析出的当前用户为准
- RAG 检索按 `visibility`、`tenant_id`、`user_id` 和 metadata 做过滤

## 技术栈

后端：

- FastAPI
- SQLAlchemy
- Alembic
- Pydantic
- PyJWT
- Redis
- httpx
- scikit-learn
- pytest

前端：

- React
- Vite
- TypeScript
- React Router
- Axios
- Nginx

工程化：

- Docker
- Docker Compose
- Alembic migration
- Agent Eval scripts
- RAG Eval reports
- 单元测试与回归测试

## 目录结构

```text
app/
  agent/                 Agent Runtime、Planner、Tool、Guardrail、Trace、Failure Policy
  core/                  环境变量和基础配置
  db/                    SQLAlchemy session、ORM models
  dependencies/          FastAPI 依赖注入和鉴权
  rules/                 低空作业规则引擎和任务类型配置
  schemas/               API 请求响应模型
  services/              天气、评估、推荐、比选、RAG、记忆、审计等业务服务
alembic/                 数据库迁移
frontend/                React + Vite 前端控制台
tests/                   后端单元测试和集成测试
evals/                   Agent/RAG 评测样例和报告
scripts/                 Eval、管理员初始化和辅助脚本
docs/                    设计文档、部署说明和阶段总结
data/                    本地 SQLite、样例数据和知识库索引
```

## 前置依赖

- Python 3.11
- Node.js 与 npm
- Docker 与 Docker Compose
- 和风天气 API Key
- 可选：DeepSeek / OpenAI 兼容 API Key，用于 LLM 结构化解析

## 快速启动

### 1. 后端本地启动

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn main:app --reload
```

后端默认地址：

```text
http://localhost:8000
```

常用入口：

```text
http://localhost:8000/health
http://localhost:8000/docs
```

### 2. 前端本地启动

```powershell
cd frontend
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

### 3. Docker Compose 启动

```powershell
Copy-Item .env.docker.example .env
docker compose up -d --build
```

访问：

```text
前端：http://localhost:5173
后端：http://localhost:8000
OpenAPI：http://localhost:8000/docs
```

如需初始化管理员账号：

```powershell
docker compose --profile tools run --rm admin-init
```

管理员账号读取 `.env` 中的：

```env
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=change-me-before-deploy
```

首次运行前应替换默认 JWT secret 和管理员密码。

## 环境变量

核心配置：

```env
APP_ENV=local
APP_PORT=8000
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DATABASE_URL=sqlite:///./data/drone_agent.db
JWT_SECRET_KEY=replace-with-random-secret
SESSION_MEMORY_BACKEND=ttlcache
REDIS_URL=redis://localhost:6379/0
```

天气服务配置：

```env
QWEATHER_API_KEY=your_qweather_api_key
QWEATHER_GEO_BASE_URL=https://geoapi.qweather.com
QWEATHER_WEATHER_BASE_URL=https://devapi.qweather.com
QWEATHER_WARNING_BASE_URL=https://devapi.qweather.com
```

LLM 可选配置：

```env
LLM_ENABLED=false
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=your_deepseek_api_key
NL_PARSER_MODE=rule
```

默认建议保持：

```env
LLM_ENABLED=false
NL_PARSER_MODE=rule
```

需要启用 DeepSeek 结构化解析时，可以切换为：

```env
LLM_ENABLED=true
NL_PARSER_MODE=hybrid
```

## API 示例

鉴权说明：

- `/auth/register`、`/auth/login` 用于创建普通用户和获取 token。
- `/agent/*`、`/users/*`、`/admin/*` 需要登录鉴权。
- `/admin/*` 仅允许管理员访问。
- 部分 `/cruise/*` 结构化接口保留为业务调试和服务集成入口，具体权限策略以代码实现为准。
- 普通用户可通过注册接口创建；管理员通过 `admin-init` 初始化，或由已有管理员授权。

### 注册

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123456","display_name":"Demo User"}'
```

### 登录

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123456"}'
```

### Agent 自然语言入口

```bash
curl -X POST http://localhost:8000/agent/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "query": "帮我判断明天下午深圳湾适不适合巡航",
    "session_id": "demo-session-001"
  }'
```

### 单地点评估

```bash
curl -X POST http://localhost:8000/cruise/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "location": "深圳湾",
    "date": "2026-08-11",
    "start_time": "14:00",
    "end_time": "17:00",
    "task_type": "巡航"
  }'
```

### 知识检索

```bash
curl -X POST http://localhost:8000/knowledge/advice/retrieve \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "query": "强风天气下无人机巡航有什么操作建议",
    "location": "深圳",
    "task_type": "巡航",
    "top_k": 5
  }'
```

## 测试与 Eval

项目包含后端单元测试、前端构建检查、Agent Eval 和 RAG Eval。Eval 脚本用于评估工具选择、多轮状态、失败恢复和 RAG 召回质量，可输出 Markdown / JSON 报告。

### 后端测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### 前端构建

```powershell
cd frontend
npm run build
```

### Agent Eval

```powershell
.\.venv\Scripts\python.exe scripts/tool_calling_eval.py
.\.venv\Scripts\python.exe scripts/multi_turn_state_eval.py
.\.venv\Scripts\python.exe scripts/failure_recovery_eval.py
```

### RAG Eval

```powershell
.\.venv\Scripts\python.exe scripts/rag_eval.py
```

详细指标建议查看 `evals/reports/` 下生成的报告。

## 关键设计取舍

### 规则引擎 vs LLM

适飞判断必须稳定、可复现、可测试，所以由规则引擎负责。LLM 只负责自然语言解析和表达优化，不能直接生成安全结论。

### RAG vs 规则结论

RAG 用于补充操作建议和政策提示，不改变适飞 / 慎飞 / 禁飞结论。低置信或空召回时返回保守提示。

### 自然语言入口 vs 结构化接口

自然语言入口提升交互体验，但结构化 API 保留，便于测试、前端调用和系统集成。

### TTLCache vs Redis vs Database Memory

TTLCache 适合本地单进程开发，Redis 适合 Docker 和多实例共享短期上下文，Database 适合持久化会话上下文。业务层通过统一接口使用，不直接耦合底层实现。

### SQLite vs PostgreSQL

SQLite 适合本地运行和功能验证。生产部署和高并发写入场景更适合 PostgreSQL，并需要连接池、备份和迁移流程。

## 当前边界

这个项目应被定义为“可运行的低空作业气象决策原型”，不是生产级航空安全系统。

当前限制：

- 天气数据只接入一个第三方来源，气象准确性依赖外部服务。
- 规则阈值是工程化原型，不等同于权威适航标准或监管审批结论。
- RAG 知识库是样例知识库，不应包装成实时权威政策库。
- LLM 默认关闭，主要用于结构化解析和解释增强。
- SQLite 适合本地运行和功能验证，不适合高并发写入场景。
- 当前 Docker Compose 更适合本地联调和服务器部署前验证，生产化还需要独立 Nginx 反代、HTTPS、PostgreSQL、监控告警和备份策略。

## Roadmap

工程化方向：

- 增加 GitHub Actions，运行后端测试、前端构建和最小 Agent/RAG Eval。
- 补充架构图、Agent 执行链路图和安全边界图。
- 增加 `docs/eval-summary.md`，把 Eval 指标整理成可读质量报告。
- 将服务器部署配置拆分为 `docker-compose.prod.yml`。
- 迁移高并发验证环境数据库到 PostgreSQL。

功能方向：

- 增加可配置规则集，支持通过结构化表格维护任务阈值。
- 在评估结果中输出 `rule_hits`，展示实际值、阈值、命中规则和风险等级。
- 增加规则版本管理和规则来源字段，历史评估保存当时规则快照。
- 将 RAG 知识库从静态 JSON 升级为可维护后台。
- 增加更多异常场景和权限场景的自动化测试。
