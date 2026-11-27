# CI/CD 说明

## 目标

本项目当前实现的是 CI 质量门禁，不包含自动生产部署。

- CI：在 GitHub Actions 临时 runner 中执行后端测试、PostgreSQL API 回归、数据库迁移、Docker Compose 配置校验、快速 Agent/RAG Eval、前端测试及 lint/build、Session 真实依赖集成回归。
- CD：服务器部署仍按 [Docker部署说明.md](Docker部署说明.md) 手动执行，避免 CI 误改生产或演示环境。

CI 和 Docker 默认验证 Agent Loop 主链路：

```env
AGENT_RUNTIME_MODE=loop
```

## 2026-11-27 门禁版本核对

本节提交记录对应修改前的本地 `main@4cebe72`；本轮工作区中的 Eval 修补见下文“本轮修补与验证”。项目没有独立的质量门禁版本号，需分别看 CI 工作流与其中各专项的更新记录，不能把 `eval_fast` 等同于全部 CI。

| 层级 | 修改前版本依据 | 覆盖及边界 |
|---|---|---|
| CI 工作流 | `.github/workflows/ci.yml` 最近修改为 2026-11-25 的 `129a92d` | 延续 11 月 24 日的浏览器、Session 等门禁，并把请求预算和 ToolExecutor 测试加入 PostgreSQL 专项 |
| 建单幂等与任务版本 | `51064ba`、`cdbb72d` | 重复/并发建单、请求冲突、响应丢失恢复、评估期间取消或修改、旧版本结果不得覆盖新状态；后端全套和 PostgreSQL 专项都会执行相关测试 |
| 前端取消与 Session 集成 | 2026-11-24 的 `f7a5fc0` | 五个 Chromium 页面场景；Push/PR 执行八个 Session 场景，手动触发执行十四类各三次。天气固定，Session 演练的应用进程、PostgreSQL 和 Redis 真实运行 |
| Tool Calling 快速 Eval | 四项阈值始于 2026-08-07 的 `c2aa314`，8 月 19 日 `ffbda62` 补充断言错误信息 | 仍为 Planner 级评测；未增加总通过率、追问通过率、fallback 准确率和关键类别全通过断言 |
| RAG 快速 Eval | `tests/test_eval_regression.py` 最近修改为 2026-11-20 的 `db85a63` | Hybrid 检索质量、过滤、权限、无答案 fallback 和延迟；这里的更新没有改变 Tool Calling 四项断言 |

幂等性及前后端状态不一致修复时新增的门禁持续保留。本轮在此基础上补齐 Tool Calling Eval 的执行层级与断言：默认入口已执行真实 AgentLoop、Planner、ToolExecutor 和 Guardrail，业务 handler 使用固定夹具；因此其通过不代表实际天气服务或业务持久化已经完成端到端验证。

本轮更新了 Eval、样例、测试和 workflow；下文验收记录为本地结果，远程 Actions 和部署状态需另外核验。真实模型回归入口已加入，但实际 DeepSeek 调用因自动审批拒绝而未完成；离线模型夹具的通过情况单独标识。

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

普通 CI 不依赖真实 LLM 输出，不依赖真实天气 API，不读取本地 `.env`。Docker Compose 校验前会用 `.env.example` 生成临时 `.env`。显式勾选 `run_deepseek` 的手动专项另行使用 DeepSeek，天气仍固定；下文说明其隔离与凭据配置。

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
- 请求预算与工具超时，包括解析和工具共享请求预算、超时后禁止迟到建单或修改提交、已提交建单的幂等恢复、有界执行容量、天气重试/LLM 调用使用剩余预算，以及比选分支的预算与 Trace 隔离。对应 `tests/test_execution_budget.py` 和 `tests/test_tool_executor.py`，已加入 PostgreSQL 专项。

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

共享 API 夹具默认使用 SQLite 内存库，显式传入 `--api-db=postgresql` 时要求 PostgreSQL 连接，在每例独立的随机 schema 中建表，结束后删除该 schema；这样工作线程的独立连接可以看到真实提交。幂等性与任务版本专项还需设置 `IDEMPOTENCY_TEST_DATABASE_URL`；CI 将其设为同一专用 PostgreSQL 测试库，两组专项在每例随机 schema 内执行并清理，未设置时使用临时 SQLite 文件。

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

四个快速门禁当前实际断言如下；未列出的报告指标不自动构成门禁：

| 专项 | 实际硬断言 |
|---|---|
| Tool Calling | 至少九条基线、总通过率 `== 1.0`；追问、追问续接、Guardrail、fallback 和追问/权限/修改/工具失败类别通过率均 `== 1.0`；禁止工具违规率 `== 0`；保留意图 `>= 0.95`、工具选择 `>= 0.90`、漏调 `<= 0.05` |
| 多轮状态 | 非空且总通过率 `== 1.0`；追问续接、修改字段和工具失效准确率均 `== 1.0`；保留状态继承、状态覆盖、工具输入一致性及 Session 隔离 `>= 0.95`，上下文污染率 `== 0` |
| 失败恢复 | 非空且总通过率 `== 1.0`；不编造、结构化错误完整性、可重试判断均 `== 1.0`；保留失败分类、恢复动作、fallback 决策及 Trace 错误覆盖 `>= 0.95`，权限绕过率 `== 0` |
| RAG Hybrid | 非空；Recall@K、Hit@K 均 `>= 0.70`；metadata filter `>= 0.95`；权限泄露率 `== 0`；fallback 通过率 `== 1.0`；P95 延迟 `<= 500ms` |

### 修补前：Tool Calling 7/9 与门禁通过的复现

2026-11-27 在上述未修改代码上，显式设置 `LLM_ENABLED=false`、`NL_PARSER_MODE=rule`、`AGENT_RUNTIME_MODE=loop`，运行默认 Tool Calling Eval 和 `pytest -m eval_fast -q`：前者 **7/9**，后者 **4 passed**。报告保存在本机 `data/eval-reports/tool-calling-confirmed-20261127/`，该目录被 Git 忽略；本次没有覆盖仓库中的历史报告。

| 指标 | 修补前结果 | 修补前 Tool Calling 门禁是否检查 |
|---|---|---|
| 意图准确率 | 100% | 是，要求至少 95% |
| 工具选择准确率 | 100% | 是，要求至少 90% |
| 缺失工具调用率 | 0% | 是，要求不高于 5% |
| 禁止工具违规率 | 7.14%（1/14） | 是，但允许不高于 10%，所以该次违规未触发失败 |
| 总通过率 | 77.78%（7/9） | 否 |
| 追问通过率 | 0%（0/1） | 否 |
| fallback 准确率 | 88.89%（8/9） | 否 |

两条失败需要分别解释：

- `agent_clarification_missing_location_001`：输入“明天下午能飞吗？”实际生成 `ask_clarification`，缺失字段为 `location`；样例期望为 `location` 和 `task_type`。现行规则 Parser 会把未指定的评估任务类型默认为 `cruise`，因此这是预期与解析契约不一致，不能说成系统没有追问。后续需明确：沿用默认巡航时修正样例；若产品要求强制确认任务类型，则先统一解析契约及相关测试。
- `agent_permission_denied_001`：默认入口 `_run_planner_case()` 只产生 `query_user_history` 计划，并将计划映射为模拟成功结果，没有经过 AgentLoop、ToolExecutor 或 Guardrail；因此不能据此判断实际权限拦截成功，也不能据此断言已经读取其他用户数据。`expected_guardrail` 当前还没有被 `evaluate_case()` 检查。

权限样例还存在输入边界：规则 Parser 的历史查询载荷不提取目标 `user_id`，历史工具用登录上下文限定用户。后续接通 Guardrail 时，应区分“自然语言请求其他用户数据的行为”和“候选工具载荷伪造 `user_id` 的拒绝”，分别核对实际数据作用域和 Guardrail 错误码，不能预设仅增加执行层就必然得到样例中的拒绝结果。

另有两个评测边界：`force_tool_error` 在默认路径中直接构造失败响应，没有真实执行天气工具；`expected_result_keywords`、`expected_error_type` 等字段也未参与当前单例通过判定。默认脚本即使有失败样例也正常退出，手动 `full-eval` job 生成报告不等于它会因总通过率不足而失败。

### 本轮修补与验证

已实施的修改：

1. 默认确定性 Eval 执行真实 AgentLoop、ToolExecutor 和 Guardrail，克隆实际工具权限规格，仅替换业务 handler 与 Trace 存储；记录实际 handler 执行、被拦截的尝试、参数、错误码及故障注入。缺参负例通过实际追问链路，再验证同 Session 补充地点后的参数和工具执行。
2. 评估沿用默认 `cruise` 契约，缺参样例只期待 `location`，禁止无必要的额外追问。权限负例明确标记伪造候选 `user_id` 的注入，断言错误码及 handler 未执行；不将该结果表述为自然语言目标用户提取能力。
3. Tool Calling、多轮状态和失败恢复的报告命令遇到失败用例或空集时返回 `1`，仍保留 JSON/Markdown。RAG 默认对 BM25/Hybrid 执行既有指标阈值，实验检索器的漏检继续列入报告；单独选择其他检索器时应用同一组指标阈值。RAG Eval 不调用模型相关性复核，保持确定性。
4. CI 与 Docker 完整 Eval 汇总所有脚本和快速门禁的失败，避免后续成功命令覆盖先前失败退出码；CI 无论通过或失败都上传现有报告。Docker 测试/Eval 明确关闭模型，防止业务 `.env` 影响确定性门禁。
5. LLM 缺参错误保留已解析字段、意图、接口和解析来源，供实际追问后续接使用；结构化追问响应返回 `missing_fields`。完整参数请求仍经过原 Schema 校验。
6. 新增 `scripts/deepseek_regression_eval.py` 和五类显式手动模型场景，固定天气 provider 响应，使用临时 SQLite、隔离测试用户和数据库 Session，实际执行 Orchestrator 与业务工具。报告保存模型响应、工具输入、响应与状态断言；未收到真实模型响应、场景失败或未执行完整五类均返回失败。

本地确定性 Tool Calling 已由修补前 **7/9** 提升为 **9/9**。`tests/test_eval_cli.py` 用错误预期及空集验证报告命令失败退出；`tests/test_deepseek_harness.py` 用明确标识的离线模型输出验证五类场景和实际业务工具，禁止访问网络。离线夹具通过不代表真实 DeepSeek 通过。

2026-11-27 本地验收：后端全套 **519 passed、5 skipped**（五个 live 场景按默认设置跳过），其中包含八个错误预期/空集 CLI 负例；Tool Calling **9/9**、多轮状态 **15/15**、失败恢复 **7/7**，RAG BM25 **10/10**、Hybrid **11/11**。本次保存的 TF-IDF **7/9** 和 Mock Embedding **8/10** 仍有漏检，不纳入生产检索器完整通过结论。Workflow YAML、Compose 配置和 `git diff --check` 通过；未运行远程 Actions。全套日志为本机 `data/eval-reports/eval-backend-20261127.log`，其他新报告在 `data/eval-reports/eval-fixed-20261127/`；Tool Calling 报告已同步到 `evals/reports/`。

真实模型专项包含以下断言：

| 场景 | 应验证内容 |
|---|---|
| 缺参续接 | 首轮追问且不执行业务工具；补充后继承已有字段，工具参数完整并得到预期结果 |
| 修改条件 | 地点、时段、任务类型的修改覆盖旧值，保留日期，最终评估使用新条件 |
| 任务操作 | 建单、评估、推荐/选窗、执行前复核的任务引用、参数、版本及数据库状态与最终响应一致；重试不重复建单 |
| 模型格式异常 | 收到模型响应后注入无效 JSON，验证不会执行工具、请求天气或写入评估；明确标注注入，不能冒充模型自然发生的失败 |
| 规则回退 | 在收到真实模型响应后受控注入格式错误，验证 hybrid 的 `llm_fallback_rule` 来源、规则工具参数、最终业务结果和状态；与模型自然输出的正常样例分别记录 |

普通 `pytest` 自动跳过五个 live 场景；不会把跳过当作真实模型通过。显式运行：

```powershell
.\.venv\Scripts\python.exe scripts/deepseek_regression_eval.py --env-file .env
```

也可通过进程环境设置 `LLM_MODEL` 和 `LLM_API_KEY`/`DEEPSEEK_API_KEY`，省略 `--env-file`；`--model` 可显式选择待测模型。脚本将合成请求和隔离会话上下文发送给 DeepSeek，只让任务解析使用模型，解释器和知识相关性复核不调用模型。临时数据库不会复用配置文件中的业务库；报告保存在 `data/eval-reports/deepseek/<run_id>/`，不保存凭据。

GitHub Actions 手动触发时勾选 `run_deepseek`，并填写 `deepseek_model` 或设置 repository variable `DEEPSEEK_EVAL_MODEL`，凭据使用 repository secret `DEEPSEEK_API_KEY`。不勾选时保持原确定性流程；勾选后缺模型或凭据会失败，不静默跳过。证据 artifact 为 `deepseek-regression-evidence`。

本机实际请求未通过网络沙箱，随后外网执行又被自动审批拒绝，理由为尚需明确授权外发测试请求；保存的首次运行记录为 0/5、没有收到真实模型响应，不能作为模型能力失败或验收通过的结论。当前真实模型验收待外发授权和可用网络后执行。

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
