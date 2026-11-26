# 知识发布、撤回与暂停验收

日期：2026-11-26。基于本地 `129a92d` 后的工作区修改；未将本次结果标记为历史 RAG 指标。

## 最终结果

| 检查 | 结果 |
| --- | --- |
| 后端完整测试集 | 503 passed，12 warnings |
| 其中版本发布与运行时控制回归 | 21 passed |
| 其中管理员知识 API 回归 | 7 passed |
| 前端 lint | 通过 |
| 前端 TypeScript / Vite 构建 | 通过 |
| 前端 Node 单测 | 6 passed |
| Playwright Chromium 浏览器回归 | 9 passed，包含新增知识管理 4 项及原任务取消 5 项 |
| Python 编译检查、git diff --check | 通过 |

后端最终一次全量耗时 257.34 秒。警告包括既有 Starlette 弃用提示及任务结果的 Pydantic 序列化提示，无测试失败。

## 关键覆盖

- 在读取索引和读取文档之间发布新版本，同次查询继续读取完整旧版。
- 新版构建暂停时仍可查询旧版，发布后的新查询使用新版；Hybrid 两路版本一致。
- Embedding 构建中途失败、构建文件不匹配、发布指针写入失败均保留当前版本。
- 查询自动重建失败继续使用同源、同模型的有效旧版。
- 跨线程及子进程的并发构建互斥；构建进程退出后锁可再次获取。
- 普通修改待发布，构建期间发生的新修改仍保留待发布标记。
- 立即撤回不等待重建，不影响其他条目；失败重建不能解除撤回。
- 重新启用后仍需正确版本成功发布；旧版本不会随修正版发布重新开放。
- 撤回或权限修改的数据库提交失败时，限制保守保留；发布旧数据库内容不能解除限制。
- 权限收紧立即生效，扩大权限待发布。
- 全局暂停只能由管理员设置和恢复，成功或失败的重建均不恢复检索。
- 相关性复核期间撤回或暂停，在返回前排除；使用撤回知识生成的解释被丢弃。
- 浏览器验证保存待发布、单条撤回、全局暂停/恢复，以及成功/失败发布的提示。

## 命令与证据

后端使用 Windows Python 3.11、临时 SQLite、独立索引和 `SESSION_MEMORY_BACKEND=ttlcache`。真实 LLM 关闭，规则解析开启：

```powershell
$env:LLM_ENABLED='false'
$env:NL_PARSER_MODE='rule'
$env:AGENT_RUNTIME_MODE='loop'
$env:SESSION_MEMORY_BACKEND='ttlcache'
$env:DATABASE_URL='sqlite://'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=tmp/knowledge-final --junitxml=data/eval-reports/knowledge-publication-20261126/backend.xml
```

原始后端日志和 JUnit 报告保存在 git 排除的运行目录：

- [backend.log](../../../data/eval-reports/knowledge-publication-20261126/backend.log)
- [backend.xml](../../../data/eval-reports/knowledge-publication-20261126/backend.xml)

前端在 `frontend/` 运行 `npm run lint`、`npm run build`、`npm test` 和 `npx playwright test`。浏览器接口使用固定 HTTP 夹具，API 权限和真实检索由后端测试单独验证。首次浏览器运行发现发布失败提示被列表刷新清掉，修复更新顺序后重跑通过；最后调整维护提示框布局后再次通过。

后台页面截图见 [knowledge-publication.png](knowledge-publication.png)。临时测试数据库和索引已清理，原始业务数据库和已有索引未用于测试。

本次未验证远程 GitHub Actions、Linux 文件锁分支、PostgreSQL 专项、真实模型、真实天气供应商或服务器部署。不能据此推断生产 SLA 或生产延迟。
