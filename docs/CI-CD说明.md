# CI/CD 说明

## 目标

本项目当前实现的是 CI 质量门禁，不包含自动生产部署。

- CI：在 GitHub Actions 临时 runner 中执行后端测试、数据库迁移、Docker Compose 配置校验、快速 Agent/RAG Eval。
- CD：服务器部署仍按 `docs/Docker部署说明.md` 手动执行，避免 CI 误改生产或演示环境。

## 触发方式

`.github/workflows/ci.yml` 会在以下场景触发：

- `push` 到 `main`
- 向 `main` 发起 `pull_request`
- 在 GitHub Actions 页面手动执行 `workflow_dispatch`

## CI 环境变量

CI 固定使用稳定、可重复的测试配置：

```text
LLM_ENABLED=false
NL_PARSER_MODE=rule
AGENT_RUNTIME_MODE=loop
DATABASE_URL=sqlite:///./data/ci-test.db
```

CI 不依赖真实 LLM 输出，不依赖真实天气 API，不读取本地 `.env`。Docker Compose 校验前会用 `.env.example` 生成临时 `.env`。

## 每次 Push/PR 必跑

GitHub Actions 的 `Backend tests` job 会执行：

```bash
python -m pip install -r requirements.txt
python -m alembic upgrade head
python -m pytest -q
python -m pytest -m eval_fast -q
docker compose --profile test --profile eval --profile tools config --quiet
```

其中：

- `python -m pytest -q` 覆盖后端单元测试、API 测试、Agent Runtime、权限过滤、规则引擎、RAG 基础链路。
- `python -m pytest -m eval_fast -q` 是 Agent/RAG 快速质量门禁。
- `docker compose ... config --quiet` 只校验 Compose 配置，不启动生产服务。

## 前端 CI

GitHub Actions 的 `Frontend lint and build` job 固定使用 Node 24，并在 `frontend/` 目录执行：

```bash
npm ci
npm run lint
npm run build
```

其中：

- `npm ci` 使用 `package-lock.json` 安装可重复依赖。
- `npm run lint` 执行 oxlint，检查 React/TypeScript 基础问题。
- `npm run build` 执行 `tsc -b && vite build`，验证类型检查和生产构建。

本地运行：

```bash
cd frontend
npm ci
npm run lint
npm run build
```

前端 CI 只做构建质量门禁，不负责部署静态资源。正式前端服务仍通过 Docker/服务器部署流程交付。

## 快速 Eval 门禁

快速 Eval 由 `tests/test_eval_regression.py` 统一设置阈值：

- Tool Calling：意图识别、工具选择、缺失工具调用、误调用工具。
- 多轮状态：状态继承、状态覆盖、工具输入一致性、上下文污染、session 隔离。
- 失败恢复：失败分类、恢复动作、fallback 决策、trace 错误覆盖、权限绕过率。
- RAG Hybrid：Recall@K、Hit@K、metadata filter、权限泄露率、P95 延迟。

本地运行：

```bash
python -m pytest -m eval_fast -q
```

Docker 运行：

```bash
docker compose --profile eval run --rm eval-fast
```

## 完整 Eval

完整 Eval 不在每次 push/PR 自动执行，只在 GitHub Actions 页面手动触发 `Backend CI` 时生成报告。

手动触发后，`Full eval reports` job 会执行：

```bash
python scripts/tool_calling_eval.py
python scripts/multi_turn_state_eval.py
python scripts/failure_recovery_eval.py
python scripts/rag_eval.py
```

生成报告目录：

```text
evals/reports/
```

GitHub Actions 会把该目录上传为 `eval-reports` artifact。

本地运行完整 Eval：

```bash
python scripts/tool_calling_eval.py
python scripts/multi_turn_state_eval.py
python scripts/failure_recovery_eval.py
python scripts/rag_eval.py
```

Docker 运行完整 Eval：

```bash
docker compose --profile eval run --rm eval-full
```

## 失败排查顺序

CI 失败时先看失败 step：

- `Run database migrations`：优先检查 Alembic migration、SQLAlchemy model、`DATABASE_URL`。
- `Run backend test suite`：优先检查普通单元测试和 API 回归。
- `Run fast Agent and RAG eval gates`：优先检查 Agent/RAG 质量指标。
- `Validate Docker Compose configuration`：优先检查 `docker-compose.yml`、profiles、`.env.example`。

Eval 失败时按指标定位：

- Tool Calling 退化：优先检查 `parser`、`planner`、Tool Registry、工具参数组装。
- 多轮状态退化：优先检查 `context_manager`、session memory、任务状态合并逻辑。
- 失败恢复退化：优先检查 `failure_policy`、fallback、trace error 记录。
- RAG 召回退化：优先检查 `retriever`、Hybrid rerank、metadata filter、权限过滤。

## 完成标准

- push/PR 后 `Backend tests` 为绿色通过。
- 工具选择退化能被 `eval_fast` 发现。
- RAG 召回、metadata filter、权限过滤退化能被 `eval_fast` 发现。
- 完整 Eval 可通过 `workflow_dispatch` 手动生成报告。
- CI 和服务器部署边界清晰，CI 不直接操作生产/演示服务器。
