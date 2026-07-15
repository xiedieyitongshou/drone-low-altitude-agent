# 低空作业气象决策 Agent

这是一个把比赛原型重构为本地可开发、可测试、可部署后端系统的项目。

项目最初基于阿里云百炼工作流搭建，核心场景是：在执行无人机巡航、巡检、悬停拍摄、测绘等低空任务前，结合逐小时天气和天气预警，给出是否适合执行任务的判断。

当前这版已经不再只是流程原型，而是一个以 **规则引擎** 为核心、以 **天气服务** 为数据来源、以 **FastAPI** 为接口入口的本地后端系统。

## 项目目标

这个项目不是做“天气查询”，而是做“任务执行决策”。

它希望回答这些问题：

- 某个地点、某个时间段是否适合执行低空任务
- 风险主要来自哪些天气因素
- 未来什么时候更适合执行任务
- 多个候选地点中先去哪一个更合适
- 历史任务为什么当时被判断为慎飞或禁飞

## 当前已完成能力

### 1. 单地点任务评估

系统已经支持：

- 输入地点、日期、时间段、任务类型
- 查询天气与预警
- 输出逐小时判断
- 输出整体结论 `适飞 / 慎飞 / 禁飞`

对应接口：

- `POST /cruise/evaluate`

### 2. 最佳执行时间推荐

系统已经支持：

- 扫描未来逐小时天气数据
- 识别连续低风险窗口
- 按“适飞优先、风险低优先、连续性优先”排序
- 返回推荐时间段和原因

对应接口：

- `POST /cruise/recommend`

### 3. 多地点任务比选

系统已经支持：

- 同一时间段内对多个地点批量评估
- 输出地点排序
- 输出 `Top-K`
- 根据不同权重模式做比选

当前比选指标包括：

- 可飞小时数
- 最长连续可飞小时数
- 最早可飞时间
- 可飞窗口质量

对应接口：

- `POST /cruise/compare`

### 4. 历史任务复盘

系统已经支持：

- 评估结果自动落库
- 保存请求、天气快照、预警快照、评估结果
- 按 `request_id` 查询历史记录

对应接口：

- `GET /cruise/history/{request_id}`

## 当前架构思路

当前项目已经形成比较清晰的三层数据结构：

### 1. Provider 原始响应层

负责接和风天气 API 原始返回。

### 2. Mapper / Adapter 层

负责把原始天气、预警数据转换为项目内部统一模型。

### 3. 内部统一模型层

规则引擎、推荐模块、比选模块、历史复盘都只依赖统一后的内部数据结构。

这层设计的意义是：

- 外部天气 API 可以变化
- 内部规则和业务逻辑尽量保持稳定

## 当前模块划分

### `app/services/weather/`

负责：

- 地点解析
- 逐小时天气查询
- 预警查询
- 原始响应标准化
- 时间段小时桶提取

### `app/rules/`

负责：

- 逐小时风险判断
- 预警修正
- 时间段汇总
- 不同任务类型阈值配置

### `app/services/recommendation/`

负责：

- 推荐时间窗口识别
- 连续低风险窗口排序

### `app/services/comparison/`

负责：

- 多地点并行评估
- 排序与 `Top-K` 输出
- 不同比选权重模式

### `app/db/`

负责：

- `SQLite + SQLAlchemy + Alembic`
- 历史任务复盘最小闭环落库

## 当前支持的任务类型

目前系统内置四类低空任务模板：

- `cruise`：巡航
- `inspection`：巡检
- `hover`：悬停拍摄
- `survey`：测绘

它们使用不同的天气阈值，因此同一气象条件下，可能得到不同风险结论。

## 当前规则思路

规则引擎保持了原型阶段的核心原则：

- 先根据逐小时天气做判断
- 再根据高风险预警做统一修正
- 最后按“最差小时原则”汇总整体结果

当前输出特点：

- 每个小时都有独立判断
- 每个小时保留风险原因
- 整体结论可解释、可回放

## 数据持久化现状

当前已经接入：

- `SQLite`
- `SQLAlchemy`
- `Alembic`

已完成的最小闭环表包括：

- `task_requests`
- `locations`
- `weather_provider_snapshots`
- `weather_hourly_snapshots`
- `weather_warning_snapshots`
- `cruise_assessments`
- `cruise_hourly_assessments`

后续正式部署阶段计划迁移到 `PostgreSQL`。

## 快速启动

### 1. 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，至少填写：

- `QWEATHER_API_KEY`
- `QWEATHER_GEO_BASE_URL`
- `QWEATHER_WEATHER_BASE_URL`
- `QWEATHER_WARNING_BASE_URL`
- `DATABASE_URL`

当前本地默认数据库：

```env
DATABASE_URL=sqlite:///./data/drone_agent.db
```

### 3. 启动服务

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

### 4. 打开接口文档

```text
http://127.0.0.1:8000/docs
```

## 当前主要接口

- `GET /health`
- `POST /cruise/weather-fetch`
- `POST /cruise/evaluate`
- `POST /cruise/recommend`
- `POST /cruise/compare`
- `GET /cruise/history/{request_id}`

## 当前状态

截至目前，项目已经完成：

- 天气服务封装
- 统一 Schema
- Mapper / Adapter 数据收口
- 本地规则引擎
- 推荐窗口模块
- 多地点比选模块
- 任务类型差异化规则
- 历史任务复盘最小闭环

后续工作重点将转向：

- 第三周剩余增强功能整理
- 更完整的历史列表与复盘能力
- Agent 化输入解析
- RAG / 知识增强解释
- 部署与演示完善
