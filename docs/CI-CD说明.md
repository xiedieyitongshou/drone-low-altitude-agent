# CI/CD 说明

## 目标

本项目当前实现的是 CI 质量门禁，不包含自动生产部署。

- CI：在 GitHub Actions 临时 runner 中执行后端测试、PostgreSQL API 回归、数据库迁移、Docker Compose 配置校验、快速 Agent/RAG Eval、前端测试及 lint/build、Session 真实依赖集成回归。
- CD：服务器部署仍按 [Docker部署说明.md](Docker部署说明.md) 手动执行，避免 CI 误改生产或演示环境。

CI 和 Docker 默认验证 Agent Loop 主链路：

```env
AGENT_RUNTIME_MODE=loop
```

## 触发方式

`.github/workflows/ci.yml` 会在以下场景触发：

- `push` 到 `main`
- 向 `main` 发起 `pull_request`
- 在 GitHub Actions 页面手动执行 `workflow_dispatch`

## CI 环境变量

SQLite 后端测试 job 使用以下配置：

```text
LLM_ENABLED=false
NL_PARSER_MODE=rule
AGENT_RUNTIME_MODE=loop
DATABASE_URL=sqlite:///./data/ci-test.db
SESSION_MEMORY_BACKEND=ttlcache
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

## PostgreSQL API 回归

`PostgreSQL API regression tests` job 在每次推送到 `main`、向 `main` 提交 PR 或手动触发时运行。GitHub Actions 为这个 job 启动临时的 PostgreSQL 16 服务，先执行 `alembic upgrade head`，再用相同的数据库运行回归测试。

- 注册和登录，包括用户名重复、错误密码、停用账号和当前账号查询。
- Profile 读写，包括写入后重新读取、用户之间的偏好隔离、默认值补全。
- 对话历史，包括登录校验、列表、搜索、分页过滤和详情的用户隔离。
- 任务评估，包括任务列表与评估历史的用户隔离、评估成功后从任务详情和历史接口读回同一结果、取消后再次评估返回 `409` 且历史记录保持原值。
- 登录后 Session 上下文，包括重新创建存储实例后恢复最新状态、同会话编号的用户隔离，以及删除过期上下文后保留聊天历史。
- 建单幂等性，包括串行/并发重试、请求冲突、用户隔离、事务回滚、提交确认或响应丢失及 Agent 中断恢复。
- 任务版本控制，包括评估/复核/推荐期间取消或修改、原子写入冲突、快照回滚、HTTP 版本契约、Agent 旧窗口及旧版本重试；取消先提交时，旧计算不得改写任务或留下成功评估。

本地复现时，将 `DATABASE_URL` 指向一个空的 PostgreSQL 测试库。从项目根目录执行：

```bash
python -m alembic upgrade head
python -m pytest -q --api-db=postgresql \
  tests/test_auth_api.py tests/test_user_profile_api.py tests/test_conversation_history_api.py \
  tests/test_history_rule_snapshot.py \
  tests/test_mission_task_execution_api.py::test_task_evaluation_readback_and_cancellation \
  tests/test_mission_task_execution_api.py::test_task_evaluation_history_requires_task_visibility \
  tests/test_session_memory.py::test_default_database_sessions_restore_latest_context_by_user \
  tests/test_session_memory.py::test_session_cleanup_checks_last_write_and_keeps_chat_history \
  tests/test_task_creation_idempotency.py tests/test_mission_task_versioning.py
```

共享 API 夹具默认使用 SQLite 内存库，显式传入 `--api-db=postgresql` 时要求 PostgreSQL 连接，通过事务回滚清理测试数据。幂等性与任务版本专项还需设置 `IDEMPOTENCY_TEST_DATABASE_URL`；CI 将其设为同一专用 PostgreSQL 测试库，两组专项在每例随机 schema 内执行并清理，未设置时使用临时 SQLite 文件。

## 前端 CI

GitHub Actions 的 `Frontend lint and build` job 固定使用 Node 24，并在 `frontend/` 目录执行：

```bash
npm ci
npm run lint
npm test
npx playwright install --with-deps chromium
npm run test:e2e
npm run build
```

其中：

- `npm ci` 使用 `package-lock.json` 安装可重复依赖。
- `npm run lint` 执行 oxlint，检查 React/TypeScript 基础问题。
- `npm test` 检查前端操作 ID 恢复和版本结果判断。
- `npm run test:e2e` 使用 Chromium 打开真实任务页面，点击评估与取消，控制 HTTP 响应顺序并检查列表、详情、按钮、提示和当前结果。覆盖正常评估、取消后晚到 `409`、取消后晚到旧 `200`（含相同版本）、取消后晚到旧列表刷新五个场景；冲突不会自动重放写请求。列表只应用最近一次刷新请求的响应，避免旧列表与已取消详情不一致。
- `npm run build` 执行 `tsc -b && vite build`，验证类型检查和生产构建。

浏览器用例位于 `frontend/e2e/task-cancellation.spec.ts`，使用 HTTP 夹具，不连接数据库；取消先提交的真实后端通常应返回 `409`，旧 `200` 是刻意注入的防御性场景。数据库状态和快照回滚由上述 PostgreSQL 任务版本专项独立验证，不能把前端夹具描述为浏览器到真实数据库的端到端验证。

浏览器失败时上传 `frontend-browser-failures` artifact，保留 HTML 报告、截图和 Trace，保存 7 天。

本地运行：

```bash
cd frontend
npm ci
npm run lint
npm test
npx playwright install chromium
npm run test:e2e
npm run build
```

Linux 首次安装浏览器时可加 `--with-deps` 安装系统依赖。Playwright 自动启动绑定 `127.0.0.1:4173` 的独立 Vite 进程，覆盖 API 地址为测试夹具地址，并在结束后关闭；该端口需空闲。

前端 CI 负责测试和构建，不负责部署静态资源。正式前端服务仍通过 Docker/服务器部署流程交付。

## Session 持久化与恢复门禁

`Session persistence and recovery` job 使用当前代码构建测试镜像，并通过 `docker/session_reliability.compose.yml` 启动两个独立后端、PostgreSQL 16、Redis 7 AOF 和固定天气 HTTP 服务。它不读取业务 `.env`，不映射宿主机端口，使用独立项目、网络及临时卷。

| 触发方式 | 执行范围 | 必须通过 |
|---|---|---|
| Push/PR | `--profile smoke`，8 个场景各 1 次 | 应用重启、跨实例续接、用户/会话隔离、同会话并发保护、PostgreSQL/Redis 过期、Redis 重启、Session 保存失败后的业务保留 |
| 手动 `workflow_dispatch` | `--profile full`，14 个场景各 3 次 | 上述场景及多轮修改、强杀应用、PostgreSQL 重启与中断、Redis 中断、业务提交后 Session 写入前强杀 |

每个场景的所有断言都通过才算通过；任一失败或启动超时使 job 失败，不跳过场景或自动重放业务请求。重启后的只读就绪探针允许在 90 秒内轮询，HTTP 失败及 Docker exec 传输失败会记录进场景证据；超时保留最后的失败诊断。固定天气夹具只替代外部天气数据，应用进程、HTTP、PostgreSQL、Redis 和故障动作均为真实运行。该结果不代表生产 SLA 或真实天气/模型质量。

本地复现：

```bash
docker build -t drone-low-altitude-agent:session-reliability-validation .
python scripts/session_reliability_eval.py --profile smoke
python scripts/session_reliability_eval.py --profile full
```

未指定 profile 时保持完整集默认行为；`--scenarios` 和 `--repeats` 可显式覆盖范围。结果写入 `data/eval-reports/session-reliability/`，脚本结束后清理该测试项目；CI 另有 `always()` 清理步骤，并始终上传 `session-reliability-evidence` artifact，含逐场景断言、请求/响应、数据库快照和容器日志，保存 14 天。详见 [会话可靠性验证说明](会话可靠性验证说明.md)。

2026-11-24 本地验收：浏览器 5/5、PostgreSQL CI 同款回归 67/67、最终 Session 精简集 8/8 与完整集 42/42。测试发现的旧列表覆盖问题、首轮故障演练失败及最终复测证据见 [本次验收记录](evidence/quality-gates-20261124/README.md)。这些本地结果不代表远程 Actions 已运行。

## 快速 Eval 门禁

快速 Eval 由 `tests/test_eval_regression.py` 统一设置阈值：

- Tool Calling：意图识别、工具选择、缺失工具调用、误调用工具。
- 多轮状态：状态继承、状态覆盖、工具输入一致性、上下文污染、session 隔离。
- 失败恢复：失败分类、恢复动作、fallback 决策、trace 错误覆盖、权限绕过率。
- RAG Hybrid：Recall@K、Hit@K、metadata filter、权限泄露率、fallback 通过率、P95 延迟。

RAG 门禁当前还要求 `fallback_pass_rate == 1.0`。BM25 完整样例通过与无答案行为另有 `tests/test_rag_eval.py` 覆盖；具体分母和模拟模型边界见 [RAG Eval 指标](RAG%20Eval%20测试指标设计.md)。

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

artifact 不会自动提交回仓库。pytest 调用 RAG 的 `run_eval()` 只做内存计算，不调用 `write_reports()`；只有报告脚本入口才写 Markdown/JSON。因此，实现或测试更新后，仓库中的旧报告仍可能未同步。

目前仓库 RAG 报告已于 2026-11-22 同步为 2026-11-20 保存的原始结果，不是本次新运行或新的 GitHub Actions 验证。[来源清单](evidence/rag-applicability-20261120/README.md) · [当前说明](RAG检索与无答案处理说明.md)

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

## 运行路径边界

| 路径 | 执行位置 | 目的 | 是否部署 |
|---|---|---|---|
| 本地运行 | 开发机 | 快速调试后端、前端、规则、Agent 行为 | 否 |
| Docker 运行 | 开发机或服务器 | 前后端联调、Redis 链路、部署前验证 | 手动 |
| CI 运行 | GitHub Actions runner | 自动测试、快速 Eval、Compose 配置校验 | 否 |
| 服务器部署 | 目标服务器 | 演示或准生产环境运行 | 手动 |

CI 不负责：

- 登录服务器
- 修改服务器 `.env`
- 重启生产容器
- 执行数据库生产迁移
- 上传前端静态资源到生产环境

这些操作应按 [Docker部署说明.md](Docker部署说明.md) 在服务器侧手动执行，或后续单独设计带审批的 CD 流程。

## legacy fallback 边界

CI 和 Docker 默认都验证：

```env
AGENT_RUNTIME_MODE=loop
```

`legacy` 只作为：

- 本地兼容模式。
- Agent Loop 异常 fallback 路径。
- 排查旧链路行为时的临时对照。

`legacy` 不作为 CI 主验证目标，也不作为 Docker 部署主链路。

## 失败排查顺序

CI 失败时先看失败 step：

- `Run database migrations`：优先检查 Alembic migration、SQLAlchemy model、`DATABASE_URL`。
- `Run backend test suite`：优先检查普通单元测试和 API 回归。
- `Run fast Agent and RAG eval gates`：优先检查 Agent/RAG 质量指标。
- `Validate Docker Compose configuration`：优先检查 `docker-compose.yml`、profiles、`.env.example`。
- `Run frontend lint`：优先检查 React/TypeScript 静态问题。
- `Test task cancellation in the browser`：下载浏览器失败证据，核对响应先后顺序、页面状态和版本处理。
- `Run Session persistence regression scenarios` / `Run complete Session fault scenarios`：下载 Session 证据，检查逐场景失败断言及应用/数据库/Redis 日志。
- `Build frontend`：优先检查类型错误、Vite 构建和环境变量。

Eval 失败时按指标定位：

- Tool Calling 退化：优先检查 `parser`、`planner`、Tool Registry、工具参数组装。
- 多轮状态退化：优先检查 `context_manager`、session memory、任务状态合并逻辑。
- 失败恢复退化：优先检查 `failure_policy`、fallback、trace error 记录。
- RAG 召回退化：优先检查 `retriever`、Hybrid rerank、metadata filter、权限过滤。

## 完成标准

- push/PR 后 `Backend tests` 为绿色通过。
- push/PR 后 `PostgreSQL API regression tests` 为绿色通过，包含幂等性、任务取消与版本竞争。
- push/PR 后 `Frontend lint and build` 为绿色通过。
- 前端浏览器流程验证评估期间可取消，晚到响应不能恢复已取消页面或应用旧结果。
- push/PR 后 `Session persistence and recovery` 精简集为绿色通过；手动触发时完整故障集全部通过。
- 工具选择退化能被 `eval_fast` 发现。
- RAG 召回、metadata filter、权限过滤退化能被 `eval_fast` 发现。
- 完整 Eval 可通过 `workflow_dispatch` 手动生成报告。
- CI 和服务器部署边界清晰，CI 不直接操作生产/演示服务器。
