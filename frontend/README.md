# 低空巡航决策系统前端

这是无人机低空巡航决策系统的前端展示工程，使用 `React + Vite + TypeScript` 搭建。

## 当前进度

Day 36 已完成前端基础框架：

- 初始化 `React + Vite + TypeScript` 工程
- 配置 `axios` 请求客户端
- 配置 `react-router-dom` 页面路由
- 新增系统状态页，请求后端 `/health`
- 预留 Agent 对话、单地点评估、推荐窗口、多地点比选、历史记录页面

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

## 构建

```bash
npm run build
```

构建产物输出到：

```text
frontend/dist/
```
