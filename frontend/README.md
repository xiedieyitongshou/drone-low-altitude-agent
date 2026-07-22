# 低空巡航决策系统前端

这是无人机低空巡航决策系统的前端展示工程，使用 `React + Vite + TypeScript` 搭建。

## 当前进度

Day 36 已完成前端基础框架：

- 初始化 `React + Vite + TypeScript` 工程
- 配置 `axios` 请求客户端
- 配置 `react-router-dom` 页面路由
- 新增系统状态页，请求后端 `/health`
- 预留 Agent 对话、单地点评估、推荐窗口、多地点比选、历史记录页面

Day 37 已完成 Agent 对话页：

- 支持填写自然语言任务请求
- 支持填写 `session_id` 和 `user_id`
- 调用后端 `/agent/query`
- 展示 `explanation`
- 折叠展示 `parsed`、`composed`、`result`
- 展示 `context_used` 和 `conversation_id`

Day 38 已完成单地点评估页：

- 支持填写地点、日期、时间段、任务类型和任务目的
- 调用后端 `/cruise/evaluate`
- 展示整体结论和 `request_id`
- 展示逐小时评估结果
- 展示风险原因和天气预警

Day 39 已完成推荐窗口页：

- 支持填写地点、日期、任务类型、扫描小时数和最小窗口小时数
- 调用后端 `/cruise/recommend`
- 展示推荐窗口排名、时间段、持续时长和风险分数
- 展示推荐理由和排序策略
- 支持无可飞窗口空状态提示

Day 40 已完成多地点比选页：

- 支持输入多个候选地点
- 调用后端 `/cruise/compare`
- 展示推荐地点和排序原因
- 展示地点排名、综合得分、风险分数
- 展示可飞小时数、最长连续可飞小时和最佳窗口

Day 41 已完成历史查询与复盘页：

- 支持输入 `request_id`
- 调用 `/cruise/history/{request_id}`
- 调用 `/cruise/history/{request_id}/composed`
- 展示历史任务请求、评估结果和统一解释
- 支持 loading、错误提示和空结果状态

## 本地启动

先启动后端服务：

```bash
uvicorn main:app --reload
```

再启动前端：

```bash
cd frontend
npm install
npm run dev
```

默认情况下，前端会请求：

```text
http://localhost:8000
```

如需修改后端地址，复制 `.env.example` 为 `.env.local`：

```bash
cp .env.example .env.local
```

然后修改：

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Agent 对话页测试

先提交完整请求：

```text
帮我评估深圳明天下午2点到5点是否适合日常巡航
```

保持同一个 `session_id`，再提交省略表达：

```text
那明天下午呢
```

如果后端上下文继承生效，响应中的 `context_used` 会变为 `true`。

## 构建

```bash
npm run build
```

构建产物输出到：

```text
frontend/dist/
```
