# Agent 化输入输出规范

本文档用于固定 Agent 层和业务决策层之间的接口边界。当前重点不是让 Agent 直接替代规则引擎，而是让自然语言输入、会话上下文、统一输出都具备稳定契约。

## 1. 设计原则

### 1.1 Agent 不直接做天气决策

Agent 层负责：

- 理解自然语言输入
- 提取任务参数
- 继承会话上下文
- 选择对应业务链路
- 组织统一响应

Agent 层不负责：

- 直接根据天气自由推理能不能执行

真正的业务判断仍由以下模块负责：

- 规则引擎
- 推荐模块
- 多地点比选模块
- 历史复盘查询模块

### 1.2 Agent 只编排标准业务接口

当前 Agent 层应优先调用：

- `POST /cruise/evaluate`
- `POST /cruise/recommend`
- `POST /cruise/compare`
- `GET /cruise/history/{request_id}`

### 1.3 输出分为业务结果和统一摘要两层

统一约定：

- `result`：保留业务接口原始结构化结果
- `composed`：面向前端和后续 LLM 的统一消费结构

## 2. 当前 Agent 入口

### 2.1 统一自然语言入口

当前统一入口：

- `POST /agent/query`

该入口负责完成：

- 自然语言解析
- 上下文补全
- 意图识别
- 下游接口路由
- 统一业务响应生成

### 2.2 当前支持意图

- `evaluate`
- `recommend`
- `compare`

## 3. 输入规范

### 3.1 Agent 请求外层结构

```json
{
  "session_id": "demo-001",
  "query": "明天上午6点到9点深圳湾适合巡航吗"
}
```

字段说明：

- `session_id`：可选，会话标识，用于上下文继承
- `query`：必填，自然语言请求

### 3.2 评估意图结构化结果

```json
{
  "intent": "evaluate",
  "location": "深圳湾",
  "date": "2026-07-18",
  "start_time": "06:00",
  "end_time": "09:00",
  "task_type": "cruise",
  "purpose": "明天上午6点到9点深圳湾适合巡航吗"
}
```

### 3.3 推荐意图结构化结果

```json
{
  "intent": "recommend",
  "location": "深圳",
  "date": "2026-07-18",
  "task_type": "survey",
  "purpose": "未来72小时深圳什么时候最适合测绘",
  "scan_hours": 72,
  "min_window_hours": 2
}
```

### 3.4 比选意图结构化结果

```json
{
  "intent": "compare",
  "locations": ["深圳", "广州", "珠海"],
  "date": "2026-07-18",
  "start_time": "06:00",
  "end_time": "09:00",
  "task_type": "inspection",
  "purpose": "深圳、广州和珠海明天早上6点到9点哪个更适合先去巡检",
  "top_k": 3,
  "comparison_mode": "default"
}
```

## 4. 会话上下文规范

### 4.1 当前实现

当前使用：

- `TTLCache`
- 按 `session_id` 存最近有效上下文

上下文字段包括：

- `intent`
- `location`
- `locations`
- `date`
- `start_time`
- `end_time`
- `task_type`
- `scan_hours`

### 4.2 当前补全规则

- 当前轮显式提取到的字段优先
- 当前轮缺失字段才从会话上下文补
- 如果当前轮和上下文都没有关键字段，则返回结构化错误

## 5. 输出规范

### 5.1 Orchestrator 层返回结构

`/agent/query` 当前返回：

- `success`
- `session_id`
- `intent`
- `target_endpoint`
- `parsed`
- `context_used`
- `message`
- `warnings`
- `composed`
- `result`
- `fallback`

### 5.2 统一消费结构 `composed`

当前统一响应字段：

- `scene`
- `summary`
- `overall_decision`
- `allow_execute`
- `risk_reasons`
- `recommended_windows`
- `ranked_locations`
- `history_summary`
- `details`

## 6. 当前边界与后续替换位

### 6.1 自然语言解析

当前：

- 规则 + 正则 + `dateparser`

后续可替换为：

- 大模型结构化解析

主要替换范围：

- `app/services/nl_parser.py`

### 6.2 会话记忆

当前：

- `TTLCache`
- 进程内内存缓存

后续可替换为：

- Redis 会话记忆

主要替换范围：

- `app/services/session_memory.py`

## 7. 当前阶段建议

当前阶段应继续坚持：

1. Agent 层只做解析、编排、上下文补全和统一响应
2. 业务判断仍由规则引擎、推荐、比选模块完成
3. 后续升级大模型解析或 Redis 时，不改变现有核心业务接口
