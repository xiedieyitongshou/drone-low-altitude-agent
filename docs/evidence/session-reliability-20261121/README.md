# 2026-11-21 会话可靠性证据

这些文件从真实隔离 Docker 运行结果中提取，使用合成测试账户。天气内容来自确定性 HTTP 夹具，LLM 关闭；应用、请求、数据库、Redis 和故障动作实际运行。

| 文件 | 内容 |
| --- | --- |
| `baseline-summary.json` | 修改前 14 个场景的全部断言、指标及原始文件哈希，10 个通过 |
| `baseline-failures.json` | 4 个失败场景的请求/结果摘录、数据库快照和失败断言 |
| `final-summary.json` | 修改后三轮 42 个场景的全部断言、逐类计时、请求/工具统计、镜像和源文件哈希 |
| `SR-*.json` | 最终运行第一轮的 5 个代表性完整场景：应用重启、并发、Session 保存失败、提交后崩溃、Redis 中断；含真实回包及可读回的 Trace |
| `baseline-container.log`、`final-container.log` | 各自测试项目的完整容器日志 |
| `backend-tests.log`、`eval-fast.log`、`migrations.log` | 隔离 Docker 回归原始日志 |
| `regression-runtime.json` | 回归容器的镜像、状态、命令及选定配置 |
| `manifest.json` | 上述数据文件的字节数和 SHA-256，以及本地两次原始报告的路径及哈希 |

本地完整逐例记录在 `data/eval-reports/session-reliability/{baseline,final}-20261121/`，由 Git 忽略。摘要删除了大体积 `actions`，保留所有检查的实际值和预期值；5 个代表性场景直接复制原始 JSON，没有重建 Trace。

仓库 `.gitattributes` 对本证据目录禁用换行转换，保留原始字节，确保检出后仍可按 `manifest.json` 核对 SHA-256。源文件哈希记录实测时构建上下文的实际字节；应用代码的跨平台换行转换可能使后续检出的文件哈希不同，核对运行来源时应同时使用镜像 ID。

基线初次运行尚未采集镜像 ID、源文件哈希、逐类汇总及工具统计，因此基线摘要缺少这些字段。原始日志可能包含正常故障注入的异常栈，不应将测试中的预期异常全算成验收失败。

报告中的 `run_at` 是最后一次写报告的时间（UTC+08:00）；数据库快照和容器日志时间采用 UTC。`client_received_at_monotonic` 只用于同次控制器运行内计时，不能跨运行比较绝对值。

`crash_before_session_write` 原始 `recovery_ms` 统计的是从发起建单至重启后完成数据库核验，未执行续接请求；[实测报告](../../会话可靠性实测报告.md) 已单独解释，不能和其他场景的续接恢复时间混合。

测试账户、Trace ID 和 Session ID 只用于定位这批离线证据；对应临时数据库及容器已经清理。[验证协议与复跑命令](../../会话可靠性验证说明.md)
