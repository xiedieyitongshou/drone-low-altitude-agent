# Docker 部署说明

本文档用于 Day32 本地 Docker 联调，也可以作为 Day33 服务器部署的基础。

## 1. 当前 Docker 结构

当前 Compose 启动两个服务：

- `app`：FastAPI 后端服务
- `redis`：Session Memory 的 Redis 后端

SQLite 数据库仍然使用文件方式保存：

```text
data/drone_agent.db
```

容器内路径为：

```text
/app/data/drone_agent.db
```

通过 volume 挂载：

```yaml
./data:/app/data
```

这样容器删除或重建后，SQLite 数据仍保留在本地 `data/` 目录。

## 2. 启动前准备

确认本地已有 `.env` 文件。可以复制 Docker 示例：

```powershell
Copy-Item .env.docker.example .env
```

然后填写和风天气配置：

```env
QWEATHER_API_KEY=your_qweather_api_key
QWEATHER_GEO_BASE_URL=https://your-host
QWEATHER_WEATHER_BASE_URL=https://your-host
QWEATHER_WARNING_BASE_URL=https://your-host
```

Docker Compose 会覆盖以下容器环境变量：

```env
APP_ENV=docker
DATABASE_URL=sqlite:///./data/drone_agent.db
SESSION_MEMORY_BACKEND=redis
REDIS_URL=redis://redis:6379/0
```

注意：容器内连接 Redis 不能写 `localhost`，要写 Compose 服务名 `redis`。

## 3. 启动

在项目根目录运行：

```powershell
docker compose up --build
```

后台启动：

```powershell
docker compose up --build -d
```

容器启动时会自动执行：

```powershell
python -m alembic upgrade head
```

然后启动：

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## 4. 验证

浏览器访问：

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

查看容器：

```powershell
docker compose ps
```

查看日志：

```powershell
docker compose logs -f app
docker compose logs -f redis
```

## 5. 停止

停止容器：

```powershell
docker compose down
```

停止并删除 Redis volume：

```powershell
docker compose down -v
```

注意：`docker compose down -v` 会删除 Redis volume，但不会删除本地 `data/drone_agent.db`，因为 SQLite 是通过 `./data:/app/data` 挂载的。

## 6. 当前部署边界

当前 Docker 版本适合：

- 本地演示
- API 功能联调
- Day33 服务器部署前验证

当前还没有包含：

- Nginx 反向代理
- HTTPS 证书
- PostgreSQL
- 多用户登录认证

这些内容可以放到服务器部署阶段继续补。
