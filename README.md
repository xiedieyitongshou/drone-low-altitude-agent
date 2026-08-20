# 低空作业气象决策 Agent

一个面向无人机低空作业场景的气象决策 Agent 工程项目。系统接入天气数据，结合任务类型、逐小时天气、天气预警和业务规则，判断指定地点和时间段是否适合执行低空巡航、测绘、巡检等任务，并提供推荐执行窗口、多地点比选、历史复盘、RAG 操作建议、多轮上下文和管理员审计能力。

项目核心原则是将业务安全判断与 AI 增强能力解耦：LLM、RAG 和 Memory 负责理解、补全、解释和检索增强，最终适飞 / 慎飞 / 禁飞结论由确定性规则引擎给出，保证结果可复现、可测试、可追踪。

## 项目状态

当前版本支持本地运行、Docker Compose 联调、GitHub Actions CI 门禁和前后端控制台演示。默认配置使用规则解析、SQLite、TTLCache；Docker 环境默认使用 Redis 会话记忆，并通过 `AGENT_RUNTIME_MODE=loop` 运行 Agent Loop。LLM 解析默认关闭，需要配置 API Key 后通过 `LLM_ENABLED=true` 和 `NL_PARSER_MODE=hybrid` 启用。

这个项目应被定义为“可运行的低空作业气象决策原型”，不是生产级航空安全系统。规则阈值、样例知识库和第三方天气数据都服务于工程化验证，不等同于权威适航标准或监管审批结论。

## 核心亮点

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

详细架构见：[docs/架构设计说明.md](docs/架构设计说明.md)。

## 快速启动

### 本地启动

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn main:app --reload
```

后端入口：

```text
http://localhost:8000/health
http://localhost:8000/docs
```

前端启动：

```powershell
cd frontend
npm install
npm run dev
```

前端入口：

```text
http://localhost:5173
```

### Docker Compose 启动

```powershell
Copy-Item .env.docker.example .env
docker compose up -d --build
```

访问入口：

```text
前端：http://localhost:5173
后端：http://localhost:8000
OpenAPI：http://localhost:8000/docs
```

如需初始化管理员账号：

```powershell
docker compose --profile tools run --rm admin-init
```

更多启动、测试和环境变量说明见：[docs/本地开发与测试说明.md](docs/本地开发与测试说明.md) 和 [docs/Docker部署说明.md](docs/Docker部署说明.md)。

## 演示入口

- 前端控制台：[frontend/](frontend/)
- 自然语言 Agent API：`POST /agent/query`
- 结构化评估 API：`POST /cruise/evaluate`
- 知识检索 API：`POST /knowledge/advice/retrieve`
- 管理员初始化脚本：[scripts/create_initial_admin.py](scripts/create_initial_admin.py)
- Eval 报告目录：[evals/reports/](evals/reports/)

典型演示输入：

```text
帮我判断明天下午深圳湾适不适合巡航
那换成后天上午呢
深圳湾、南山区、宝安机场附近明天下午哪个更适合先巡检？
强风天气下无人机巡航有什么操作建议？
```

## 技术栈

- 后端：FastAPI、SQLAlchemy、Alembic、Pydantic、PyJWT、Redis、httpx、scikit-learn、pytest。
- 前端：React、Vite、TypeScript、React Router、Axios、Nginx。
- 工程化：Docker、Docker Compose、GitHub Actions、Alembic migration、Agent Eval、RAG Eval、单元测试与回归测试。

## 目录结构

```text
app/                    FastAPI 后端、Agent Runtime、业务服务、鉴权、规则与 RAG
alembic/                数据库迁移
frontend/               React + Vite 前端控制台
tests/                  后端单元测试、API 测试和 Eval 快速门禁
evals/                  Agent/RAG 评测样例和报告
scripts/                Eval、管理员初始化、知识库导入和辅助脚本
docs/                   架构、部署、测试、权限、设计取舍和阶段说明
data/                   本地 SQLite、样例数据和知识库索引
docker-compose.yml      本地 Docker Compose 联调入口
```

## 文档导航

| 主题 | 文档 |
|---|---|
| 文档总览 | [docs/README.md](docs/README.md) |
| 系统架构与 Agent Runtime | [docs/架构设计说明.md](docs/架构设计说明.md) |
| 本地开发、测试与 Eval | [docs/本地开发与测试说明.md](docs/本地开发与测试说明.md) |
| Docker 部署 | [docs/Docker部署说明.md](docs/Docker部署说明.md) |
| CI/CD 与质量门禁 | [docs/CI-CD说明.md](docs/CI-CD说明.md) |
| 关键设计取舍 | [docs/设计取舍说明.md](docs/设计取舍说明.md) |
| 权限与数据隔离 | [docs/权限模型说明.md](docs/权限模型说明.md) |
| 项目完成度与能力映射 | [docs/项目完成度与能力映射.md](docs/项目完成度与能力映射.md) |

## 代码入口

| 能力 | 代码 / 测试 |
|---|---|
| Agent Loop | [app/agent/loop.py](app/agent/loop.py) |
| Planner | [app/agent/planner.py](app/agent/planner.py) |
| Tool Registry | [app/agent/tools.py](app/agent/tools.py) |
| Guardrail | [app/agent/guardrail.py](app/agent/guardrail.py) |
| Trace | [app/agent/trace.py](app/agent/trace.py) |
| 任务编排服务 | [app/services/task_orchestrator.py](app/services/task_orchestrator.py) |
| RAG 检索 | [app/services/knowledge_retrievers.py](app/services/knowledge_retrievers.py) |
| 规则引擎 | [app/rules/cruise.py](app/rules/cruise.py) |
| Agent 测试 | [tests/test_agent_loop.py](tests/test_agent_loop.py) |
| Eval 回归 | [tests/test_eval_regression.py](tests/test_eval_regression.py) |

## 当前边界

- 天气数据只接入一个第三方来源，气象准确性依赖外部服务。
- 规则阈值是工程化原型，不等同于权威适航标准或监管审批结论。
- RAG 知识库是样例知识库，不应包装成实时权威政策库。
- LLM 默认关闭，主要用于结构化解析和解释增强。
- SQLite 适合本地运行和功能验证，不适合高并发写入场景。
- 当前 Docker Compose 更适合本地联调和服务器部署前验证，生产化还需要独立 Nginx 反代、HTTPS、PostgreSQL、监控告警和备份策略。
