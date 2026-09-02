# Docker 部署说明

本文档覆盖两类场景：

- 本地 Docker Compose 联调。
- 从 GitHub 克隆代码后，在服务器上用 Docker Compose 私有部署。

当前 Docker 主链路默认运行 Agent Loop：

```env
AGENT_RUNTIME_MODE=loop
```

`legacy` 仅作为本地兼容模式和 Agent Loop 异常 fallback 路径，不作为 Docker 部署主链路。

## 1. 当前 Docker 结构

`docker-compose.yml` 启动四个主服务：

- `frontend`：React 前端，使用 Nginx 托管静态资源。
- `app`：FastAPI 后端服务，默认 `AGENT_RUNTIME_MODE=loop`。
- `postgres`：PostgreSQL 主数据库，使用 Docker named volume 持久化。
- `redis`：Session Memory 的 Redis 后端。

同时提供以下 profile 服务：

- `admin-init`：初始化管理员账号。
- `knowledge-import`：导入 JSON 知识库。
- `knowledge-reindex`：重建知识库索引。
- `backend-tests`：容器内运行后端测试。
- `eval-fast`：容器内运行快速 Eval 门禁。
- `eval-full`：容器内运行完整 Eval 脚本并输出报告。

Docker Compose 默认数据库为 PostgreSQL：

```env
DATABASE_URL=postgresql+psycopg://drone_agent:<password>@postgres:5432/drone_agent
```

PostgreSQL 数据保存在 Docker named volume：

```text
postgres_data
```

Redis 数据保存在 Docker named volume：

```text
redis_data
```

`./data:/app/data` 仍会挂载到后端容器，用于知识库种子、索引文件、SQLite 迁移源文件和样例数据：

```yaml
./data:/app/data
```

本地裸跑仍可使用 SQLite；Docker 部署主链路不再依赖 SQLite 运行库文件。

## 2. Dockerfile 省略了什么

根目录 `Dockerfile` 是后端镜像，`frontend/Dockerfile` 是前端镜像。它们只构建可公开的应用代码和静态资源，不包含服务器私有状态。

后端镜像包含：

- Python 运行时。
- `requirements.txt` 中声明的依赖。
- `alembic.ini` 和 `alembic/` migration。
- `app/` 后端代码。
- `data/knowledge/` 中可公开的知识库种子文件。
- `scripts/`、`evals/`、`tests/`，用于容器内工具、测试和 Eval。
- `main.py` 和 `docker/entrypoint.sh`。

后端镜像刻意不包含：

- 真实 `.env`。
- API key、JWT secret、管理员密码、数据库密码。
- SSH 私钥、证书私钥、`.pem`、`.key`。
- 服务器公网 IP、域名证书、Nginx 私有配置。
- SQLite 运行库文件 `data/drone_agent.db`。
- PostgreSQL 数据目录。
- Redis 数据目录。
- 服务器备份目录。
- 运行时生成的知识库索引 `data/knowledge/index/`。
- 压测报告、临时日志和真实演示数据导出。

前端镜像包含：

- `frontend` 源码构建出的 `dist/` 静态资源。
- Nginx 静态资源服务配置。

前端镜像刻意不包含：

- 后端服务密钥。
- 用户 token。
- 服务器真实 `.env`。
- 私有 API key。

注意：`VITE_API_BASE_URL` 是构建期变量，会被写入前端静态资源。它只能填写浏览器可访问的后端入口，例如 `http://localhost:8000`、反向代理路径或正式域名，不要写 Docker 内网服务名 `http://app:8000`。

## 3. .dockerignore 的影响

`.dockerignore` 控制 Docker build context。部署前重点检查：

- `.env` 必须被忽略，避免密钥进入镜像层。
- `data/drone_agent.db` 必须被忽略，避免把本地 SQLite 数据库打进镜像。
- `data/knowledge/index/` 建议忽略，因为索引应在目标环境生成或从数据库重建。
- `evals/reports/`、备份文件和临时文件不应进入镜像。
- `.dockerignore` 建议只使用 ASCII 路径规则，避免服务器 Docker BuildKit 对中文 ignore pattern 兼容性差。

如果 `.dockerignore` 过宽，可能导致 `COPY app ./app`、`COPY scripts ./scripts` 等步骤缺文件；如果过窄，可能把密钥、数据库或大文件打进镜像。

## 4. .env 必填项

本地联调可以复制：

```powershell
Copy-Item .env.docker.example .env
```

服务器部署推荐复制：

```bash
cp .env.production-demo.example .env
chmod 600 .env
```

必须替换的配置：

```env
APP_ENV=production-demo
APP_PORT=8000

PIP_INDEX_URL=https://pypi.org/simple
PIP_TRUSTED_HOST=
NPM_CONFIG_REGISTRY=https://registry.npmjs.org/

VITE_API_BASE_URL=http://localhost:8000
VITE_API_TIMEOUT_MS=60000
CORS_ALLOWED_ORIGINS=http://localhost:5173

QWEATHER_API_KEY=<replace-with-real-key>
QWEATHER_GEO_BASE_URL=<replace-with-real-host>
QWEATHER_WEATHER_BASE_URL=<replace-with-real-host>
QWEATHER_WARNING_BASE_URL=<replace-with-real-host>

POSTGRES_DB=drone_agent
POSTGRES_USER=drone_agent
POSTGRES_PASSWORD=<replace-with-strong-random-password>
DATABASE_URL=postgresql+psycopg://drone_agent:<same-password>@postgres:5432/drone_agent

JWT_SECRET_KEY=<replace-with-long-random-secret>
INITIAL_ADMIN_USERNAME=<replace-with-admin-username>
INITIAL_ADMIN_PASSWORD=<replace-with-strong-admin-password>

SESSION_MEMORY_BACKEND=redis
REDIS_URL=redis://redis:6379/0

LLM_ENABLED=false
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=
NL_PARSER_MODE=rule

AGENT_RUNTIME_MODE=loop
AGENT_LOG_RAW_PAYLOAD=false
```

国外服务器或网络稳定环境建议使用官方源：

```env
PIP_INDEX_URL=https://pypi.org/simple
PIP_TRUSTED_HOST=
NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
```

国内服务器如果 PyPI、npm 或 Docker 构建下载不稳定，可以切到国内源：

```env
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
PIP_TRUSTED_HOST=mirrors.aliyun.com
NPM_CONFIG_REGISTRY=https://registry.npmmirror.com/
```

这些值只影响镜像构建。修改后需要重新构建相关镜像：

```bash
docker compose build app frontend
```

私有 SSH 隧道部署建议：

```env
VITE_API_BASE_URL=http://localhost:8000
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

公网域名部署建议：

```env
VITE_API_BASE_URL=https://<your-domain>/api
CORS_ALLOWED_ORIGINS=https://<your-domain>
```

不要把以下内容提交到 GitHub：

- `.env`
- 真实 API key
- `JWT_SECRET_KEY`
- `POSTGRES_PASSWORD`
- 管理员账号密码
- SSH 私钥
- 数据库备份

## 5. 本地 Docker 启动

在项目根目录运行：

```powershell
docker compose config --quiet
docker compose up --build
```

后台启动：

```powershell
docker compose up --build -d
```

后端容器启动时会自动执行：

```powershell
python -m alembic upgrade head
```

然后启动：

```powershell
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

前端容器会先执行 Vite 构建，再由 Nginx 托管 `dist/` 静态资源。

## 6. 从 GitHub 部署到服务器

首次部署：

```bash
mkdir -p /opt/drone-low-altitude-agent
cd /opt/drone-low-altitude-agent
git clone https://github.com/<owner>/drone-low-altitude-agent.git app
cd app

cp .env.production-demo.example .env
chmod 600 .env
vim .env

docker compose config --quiet
docker compose up -d --build postgres redis
docker compose run --rm --entrypoint sh app -c 'python -m alembic upgrade head'
docker compose --profile tools run --rm admin-init
docker compose --profile tools run --rm knowledge-import
docker compose --profile tools run --rm knowledge-reindex
docker compose up -d app frontend
docker compose ps
```

首次从 GitHub 部署时，PostgreSQL volume 是空的。此时只需要执行 Alembic 创建表结构，不需要执行 SQLite 到 PostgreSQL 的历史数据迁移。

如果服务器已有部署，先备份再同步：

```bash
BACKUP=/opt/drone-low-altitude-agent/backups/pre-sync-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP/frontend" "$BACKUP/data"
cp -a .env docker-compose.yml Dockerfile "$BACKUP"/ 2>/dev/null || true
cp -a frontend/Dockerfile "$BACKUP/frontend/Dockerfile" 2>/dev/null || true
cp -a data/drone_agent.db "$BACKUP/data/drone_agent.db" 2>/dev/null || true
git diff > "$BACKUP/server-working-tree.diff"

git status --short --branch
git fetch origin
git log --oneline HEAD..origin/main
git stash push -m pre-deploy-server-local-changes
git pull --ff-only origin main
```

不要在有未识别服务器本地改动时直接执行 `git reset --hard`。

服务器本地改动管理的核心问题是：每台服务器的环境差异可能不同。例如 A 服务器需要国内源，B 服务器可能使用官方源；A 服务器通过 SSH 隧道访问，B 服务器可能走 Nginx 域名。不要把某一台服务器的临时本地改动直接回流到 GitHub 作为通用配置，除非它已经被参数化并适用于所有环境。

当前 Compose 已把 Python 和 npm 源做成 build args：国内和国外服务器只需要改 `.env` 中的源配置，不需要改 Dockerfile。

## 7. SQLite 到 PostgreSQL 迁移

当前 Docker Compose 默认使用同机 PostgreSQL。已有 SQLite 数据时，迁移前必须先备份并停止写入。

首次空库部署跳过本节；只有服务器已经存在 `data/drone_agent.db` 且需要保留历史用户、任务、会话、Trace 或知识库数据时，才执行本节。

备份：

```bash
BACKUP=/opt/drone-low-altitude-agent/backups/pre-postgres-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP"
cp -a .env data/drone_agent.db "$BACKUP"/
```

停止会写数据库的服务：

```bash
docker compose stop frontend app
docker compose up -d postgres redis
```

执行 schema migration：

```bash
docker compose run --rm --entrypoint sh app -c 'python -m alembic upgrade head'
```

执行数据迁移。迁移脚本使用 `psycopg.connect()`，需要标准 PostgreSQL URL；如果 `.env` 中是 SQLAlchemy URL `postgresql+psycopg://`，执行时转换一下：

```bash
PGURL=$(grep '^DATABASE_URL=' .env | tail -1 | cut -d= -f2- | sed 's#^postgresql+psycopg://#postgresql://#')
docker compose run --rm --entrypoint python app \
  scripts/migrate_sqlite_to_postgres.py \
  --sqlite-path data/drone_agent.db \
  --postgres-url "$PGURL" \
  --yes
```

迁移成功后再启动：

```bash
docker compose up -d app frontend
```

更多细节见 [数据库迁移说明.md](数据库迁移说明.md)。

## 8. 验证

浏览器访问：

```text
http://127.0.0.1:5173
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

服务器本机验证：

```bash
docker compose ps
docker compose logs --tail=100 app
docker compose logs --tail=100 frontend
docker compose logs --tail=100 postgres
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:5173/health
docker compose exec app env | grep '^DATABASE_URL='
docker compose exec app python -m alembic current
docker compose exec postgres pg_isready -U drone_agent -d drone_agent
```

CI 和质量门禁只能证明代码、测试、前端构建和 Compose 配置在自动化环境中通过，不能替代服务器部署后的人工检查。部署后至少要人工验证：

- 容器全部 healthy。
- 后端 `/health` 正常。
- 前端 `/health` 正常。
- 登录成功。
- `/auth/me` 返回当前用户。
- `/agent/query` 能返回业务结果。
- `/cruise/evaluate` 能返回风险评估。
- Trace 页面或接口能看到新请求记录。

确认后端使用 Agent Loop：

```bash
docker compose exec app printenv AGENT_RUNTIME_MODE
```

期望输出：

```text
loop
```

如果只通过 SSH 隧道访问，在本地机器执行：

```bash
ssh -i <private-key.pem> \
  -N \
  -L 5173:127.0.0.1:5173 \
  -L 8000:127.0.0.1:8000 \
  <ssh-user>@<server-public-ip>
```

然后访问：

```text
http://localhost:5173
http://localhost:8000/health
```

## 9. 管理员与知识库工具

初始化管理员账号：

```bash
docker compose --profile tools run --rm admin-init
```

导入知识库：

```bash
docker compose --profile tools run --rm knowledge-import
```

重建知识库索引：

```bash
docker compose --profile tools run --rm knowledge-reindex
```

管理员账号读取 `.env` 中的：

```env
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=change-me-before-deploy
```

普通 `docker compose up -d` 不会自动创建管理员账号。管理员初始化是显式操作，必须由部署者在 `.env` 中设置强密码后执行 `docker compose --profile tools run --rm admin-init`。

## 10. Docker 中运行测试与 Eval

后端测试：

```bash
docker compose --profile test run --rm backend-tests
```

快速 Eval：

```bash
docker compose --profile eval run --rm eval-fast
```

完整 Eval：

```bash
docker compose --profile eval run --rm eval-full
```

完整 Eval 报告输出到：

```text
evals/reports/
```

## 11. 压测建议

如果需要压测，优先在服务器本机执行 k6，目标使用：

```text
http://127.0.0.1:8000
```

不要通过 SSH 隧道做正式压测。隧道会混入本地网络、SSH 加密转发和客户端机器性能因素。

## 12. 停止和数据保护

停止容器：

```bash
docker compose down
```

停止并删除 Redis/PostgreSQL volume：

```bash
docker compose down -v
```

注意：`docker compose down -v` 会删除 `redis_data` 和 `postgres_data` named volumes。服务器或演示环境不要直接执行该命令，除非已经确认 PostgreSQL 数据已备份且可以丢弃。

推荐保持为服务器本地私有的内容：

- `/opt/drone-low-altitude-agent/app/.env`
- `/opt/drone-low-altitude-agent/backups/`
- `/var/backups/drone-low-altitude-agent/`
- SSH 私钥和证书私钥。
- 管理员初始化凭据。
- PostgreSQL volume。
- Redis volume。
- 真实压测账号密码和测试 token。

公开仓库只保留模板、说明和可复现脚本；真实部署状态由服务器 `.env`、Docker volume、备份和运维记录承载。

## 13. 直接部署 GitHub 版本时的注意事项

### 13.1 构建网络

GitHub 版本默认使用公开 PyPI 和 npm registry。国内服务器可能出现下载慢或超时：

- 后端卡在 `pip install --upgrade pip` 或 `pip install -r requirements.txt`。
- 前端卡在 `npm ci`。
- Docker base image 拉取慢。

可选处理：

- 配置 Docker daemon registry mirror。
- 在 `.env` 中设置 `PIP_INDEX_URL`、`PIP_TRUSTED_HOST` 和 `NPM_CONFIG_REGISTRY`。
- 所有后端镜像构建服务都应使用同一组 `PIP_INDEX_URL` / `PIP_TRUSTED_HOST` build args，包括 `app`、`admin-init`、`knowledge-import`、`knowledge-reindex`、`backend-tests`、`eval-fast` 和 `eval-full`。
- 优先使用已经参数化的 build args，避免长期维护服务器本地 Dockerfile 补丁。

### 13.2 LLM 开关

演示效果优先时可以启用 LLM：

```env
LLM_ENABLED=true
NL_PARSER_MODE=hybrid
DEEPSEEK_API_KEY=<replace-with-real-key>
```

如果部署后出现 Agent 查询超时、解析失败、第三方限流或成本不可控，先切回规则解析排障：

```env
LLM_ENABLED=false
NL_PARSER_MODE=rule
```

切换 LLM 开关只影响后端运行期，通常重启 `app` 即可：

```bash
docker compose up -d app
```

### 13.3 端口暴露

当前 `docker-compose.yml` 已把服务绑定到服务器本机：

```yaml
127.0.0.1:5173:80
127.0.0.1:8000:8000
127.0.0.1:5432:5432
127.0.0.1:6379:6379
```

这适合 SSH 隧道和本机反向代理。不要直接改成 `0.0.0.0`，除非已经配置安全组、HTTPS、认证和反向代理。

### 13.4 前端 API 地址

前端构建时会固化 `VITE_API_BASE_URL`。如果 `.env` 改了该值，必须重建前端镜像：

```bash
docker compose build frontend
docker compose up -d frontend
```

只重启前端容器不会改变已经构建进静态文件的 API 地址。

### 13.5 数据持久化

PostgreSQL 使用 Docker named volume：

```yaml
postgres_data:/var/lib/postgresql/data
```

Redis 使用：

```yaml
redis_data:/data
```

不要随意执行 `docker compose down -v`。

### 13.6 初始化和迁移顺序

推荐顺序：

1. `docker compose config --quiet`
2. `docker compose up -d postgres redis`
3. `docker compose run --rm --entrypoint sh app -c 'python -m alembic upgrade head'`
4. 首次空库部署跳过 SQLite 数据迁移；如有 SQLite 历史数据，执行迁移脚本。
5. `docker compose --profile tools run --rm admin-init`
6. `docker compose --profile tools run --rm knowledge-import`
7. `docker compose --profile tools run --rm knowledge-reindex`
8. `docker compose up -d app frontend`
9. `curl`、登录、Agent 查询、Trace 页面验证。

## 14. 运行路径边界

| 路径 | 用途 | 默认配置 | 边界 |
|---|---|---|---|
| 本地运行 | 开发和快速调试 | SQLite、TTLCache、`NL_PARSER_MODE=rule` | 不验证容器网络和 Redis 链路 |
| Docker 运行 | 前后端联调和服务器部署前验证 | PostgreSQL、Redis、`AGENT_RUNTIME_MODE=loop` | 不是完整生产部署 |
| CI 运行 | 自动质量门禁 | SQLite 临时库、LLM 关闭、快速 Eval | 不连接生产或演示服务器 |
| 服务器部署 | 手动上线或演示环境 | 基于 Docker Compose 和服务器私有 `.env` | 需要额外补 HTTPS、反代、监控、备份 |

当前 Docker 版本适合：

- 本地演示。
- 前后端完整功能联调。
- 私有服务器演示。
- 服务器部署前验证。
- 快速测试和 Eval 容器化运行。

当前还没有包含：

- 统一公网入口 Nginx 反向代理。
- HTTPS 证书。
- 监控告警。
- 自动备份。
- 自动生产部署。
