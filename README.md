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
docker compose up --build
```

后台启动：

```bash
docker compose up --build -d
```

启动后访问：

```text
前端展示页面：http://localhost:5173
后端 OpenAPI：http://localhost:8000/docs
后端健康检查：http://localhost:8000/health
```

当前 Compose 服务包括：

- `frontend`：React 前端，Nginx 托管静态资源
- `app`：FastAPI 后端，镜像内包含核心单元测试，便于容器内验证
- `redis`：会话上下文缓存

前端 Docker 构建时默认注入：

```env
VITE_API_BASE_URL=http://localhost:8000
```

因此浏览器打开 `http://localhost:5173` 后，会直接请求本机映射出来的后端 API。

如需在 Docker 后端容器内验证推荐窗口算法，可执行：

```bash
docker compose exec app python -m unittest tests.test_recommendation_windows
```

这是一个从“阿里云百炼工作流原型”重构出来的本地后端项目。原型阶段主要依赖工作流节点完成天气查询和条件判断；重构后，项目改为基于 FastAPI 的模块化后端服务，把天气数据获取、数据标准化、规则判断、推荐、比选、历史记录、自然语言入口和知识库建议拆成可维护的 Python 模块。

项目目标不是简单查询天气，而是面向无人机低空任务，回答这类问题：

- 当前地点和时间段是否适合飞行？
- 未来什么时候更适合执行任务？
- 多个地点中哪个地点优先级更高？
- 风险原因是什么？有什么操作建议？
- 用户连续追问时，能否复用上一轮上下文？

## 当前功能

- 天气服务：接入和风天气，支持地点解析、逐小时天气、天气预警获取。
- 数据标准化：通过 mapper 层把外部 API 数据转换为内部统一结构。
- 规则引擎：根据任务类型、天气指标和预警信息输出逐小时风险判断。
- 推荐窗口：线性扫描逐小时评估结果，按禁飞小时和时间断点切分连续可执行窗口，避免重复推荐重叠时间段。
- 多地点比选：支持多个地点并行评估，并按可飞小时、连续窗口、风险质量等维度排序。
- 历史记录：使用 SQLite + SQLAlchemy 保存评估请求、天气快照、预警和判断结果。
- 自然语言入口：支持基于关键词和正则的任务信息解析。
- 编排器：通过 `/agent/query` 串起解析、天气、规则、推荐、比选、响应生成。
- 会话记忆：默认使用 `cachetools.TTLCache` 保存短期上下文，支持省略表达；部署时可通过配置切换为 Redis。
- Profile Memory：当前采用单用户 `default_user` 版本，使用数据库保存默认任务偏好和常用地点。
- Conversation History：`/agent/query` 调用后自动保存自然语言请求、解析结果、响应摘要和完整响应。
- RAG 建议原型：基于本地知识库 JSON 和 TF-IDF 检索风险说明与操作建议。

## 系统结构

```text
用户输入
  ↓
自然语言解析 / 结构化请求
  ↓
Orchestrator 编排器
  ↓
Weather Provider 获取原始天气数据
  ↓
Mapper 转换为内部统一模型
  ↓
规则引擎 / 推荐模块 / 多地点比选
  ↓
历史落库 / RAG 建议检索
  ↓
统一响应输出
```

核心设计思路：

- Provider 层只负责对接外部 API。
- Mapper 层负责屏蔽不同数据源格式差异。
- Rules 层只依赖内部统一数据结构，不直接依赖和风天气原始字段。
- Service / Orchestrator 负责组织流程，不把规则细节写死在接口中。

## 主要接口

启动服务后可访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档。

- `GET /health`：健康检查。
- `POST /nl/parse`：自然语言任务解析。
- `POST /agent/query`：Agent 主入口，支持一句话完成任务调用。
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
- 会话缓存：cachetools TTLCache，预留 Redis 后端
- 记忆持久化：user_profiles、conversation_records
- 知识检索：scikit-learn TF-IDF + cosine similarity

当前 RAG 检索是可运行的轻量版本，后续可升级为 `OpenAI Embeddings + FAISS` 或 `OpenAI Embeddings + Chroma`。

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
SESSION_MEMORY_BACKEND=ttlcache
REDIS_URL=redis://localhost:6379/0
```

`.env` 不应提交到 GitHub。

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

```json
{
  "query": "帮我看一下深圳明天下午适不适合做无人机巡航",
  "session_id": "demo-session",
  "user_id": "default_user"
}
```

当前 `user_id` 默认为 `default_user`，用于单用户版本的 Profile Memory 和 Conversation History。后续接入登录或 API Key 后，可以替换为真实用户 ID。

## 当前阶段

项目已经完成从基础天气判断工具到任务决策系统的主体升级：

- 第一阶段：后端服务、天气服务、Schema、输入校验、数据 mapper。
- 第二阶段：时间提取、预警提取、规则引擎、任务阈值配置、评估接口。
- 第三阶段：推荐窗口、多地点比选、历史持久化、多任务模板。
- 第四阶段：自然语言解析、Agent 编排、会话记忆、统一响应。
- 第五阶段：已接入轻量 RAG 建议检索、Profile Memory 和 Conversation History，后续计划升级 embedding 向量库和 LLM 解释层。

## 后续计划

- 使用大模型结构化输出增强自然语言解析，保留规则解析作为 fallback。
- 引入统一 LLM 客户端，用于任务解析和最终结果解释。
- 将 TF-IDF 检索升级为 embedding + FAISS / Chroma。
