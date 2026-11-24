# 任务取消一致性与 Session 质量门禁验收

日期：2026-11-24。代码基线为 `cdbb72d` 加本次工作区改动；这是本地验收，未执行远程 GitHub Actions。

## 改动与验证

| 验证项 | 结果 | 范围 |
|---|---|---|
| Chromium 页面流程 | 5/5 | 正常评估；取消后晚到冲突；取消后晚到旧成功结果（旧版本和相同版本）；取消后晚到旧列表刷新 |
| 原有前端测试 | 6/6 | 操作 ID 恢复与版本结果判断 |
| PostgreSQL CI 同款回归 | 67/67 | 认证、Profile、历史隔离、任务读回与取消、Session 恢复与清理、幂等性、任务版本竞争 |
| 最终 Session 精简集 | 8/8 | 当前应用镜像，真实 PostgreSQL 16、Redis 7 AOF、两个后端进程 |
| 最终 Session 完整集 | 42/42 | 14 类场景各 3 次；可恢复会话 24/24；工具及 Trace 字段 288/288 |
| 演练控制器回归 | 3/3 | 就绪探针故障留档、就绪超时阻断、Compose stdout/退出码诊断 |
| 前端 lint、TypeScript、生产构建 | 通过 | 包含浏览器测试和配置的类型检查 |
| actionlint、git diff --check | 通过 | 工作流校验与补丁格式检查 |

浏览器测试使用真实页面与 API 客户端，HTTP 回包由夹具控制；它不连接数据库。数据库取消状态和事务回滚由 PostgreSQL 回归独立验证。Session 演练使用真实进程、HTTP、PostgreSQL、Redis 和故障动作，天气为固定 HTTP 夹具，LLM 关闭。

## 测试发现及修正

浏览器新增用例曾复现：评估结果已应用并发出列表刷新，用户随后取消成功；较早的列表响应最后返回，将列表改回“已评估”，详情仍为“已取消”。修复前浏览器结果为 4/5，修复后为 5/5。任务列表现在只接受最近一次刷新请求的响应，旧响应也不能覆盖错误提示或结束较新请求的加载状态。

Session 首轮完整演练为 41/42：`SR-app_kill-2` 在强杀并启动应用后的就绪阶段报 `RuntimeError: Compose exec failed: `。原控制器只保留 stderr，无法据此确定该次 Docker exec 失败的具体原因；不能将其算作成功恢复。

本次补充 Compose 子命令、退出码、stdout/stderr 诊断；只读就绪探针可在原有 90 秒期限内记录并轮询传输失败，超时仍失败，场景业务请求不自动重放。修正后的最终精简集 8/8、完整集 42/42 均通过，最终两组中没有出现 Docker exec 就绪传输失败。上述三条控制器测试另行验证了该分支及超时阻断行为。

## 证据与复现

[session-summary.json](session-summary.json) 从实际原始报告提取，保留首轮失败与最终两组结果、场景汇总、镜像 ID、源文件指纹及原始报告 SHA-256。原始逐场景请求、数据库快照和容器日志位于本地 git 排除目录 `data/eval-reports/session-reliability/quality-gates-20261124/`，其中 `full/` 为首轮、`smoke-final/` 和 `full-final/` 为最终结果。测试项目的容器、网络和专属卷已清理。

前端运行：

```bash
cd frontend
npm ci
npx playwright install chromium
npm test
npm run test:e2e
npm run lint
npm run build
```

Session 使用当前代码先构建镜像，再执行：

```bash
docker build -t drone-low-altitude-agent:session-reliability-validation .
python scripts/session_reliability_eval.py --profile smoke
python scripts/session_reliability_eval.py --profile full
python -m pytest -q tests/test_session_reliability_runner.py
```

CI 在每次 Push/PR 跑精简集，手动触发时跑完整集；失败会阻断 job，始终保留 Session 证据并清理测试项目。前端失败保留 HTML 报告、截图和 Trace。完整命令、PostgreSQL 专项配置及测试边界见 [CI 门禁说明](../../CI-CD说明.md)。
