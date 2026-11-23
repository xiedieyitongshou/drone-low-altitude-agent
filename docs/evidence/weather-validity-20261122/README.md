# 天气数据有效性回归记录

日期：2026-11-22。代码基线 `cb0c927` 加本地未提交的天气校验修改，实际文件哈希见 [manifest.json](manifest.json)。

Windows 本地 Python 3.11.5，全量运行 `python -B -m pytest -q --tb=short`：**404 passed，2 warnings，145.20 s**。[原始输出](backend-tests.log) 只做 CRLF 到 LF 的换行转换。

验证包括：六项关键指标缺失/非法值、零值与可选指标、时间缺口/重复/跨天/时区、API 无法评估、来源/预警故障、Loop/legacy 手工重试、失败条件优先级、失败任务 ID、Trace、成功历史和任务状态保留，以及推荐/比选相邻路径。

新增天气 API 测试使用 `httpx.MockTransport`，关闭真实模型调用，使用隔离测试数据库。全套用例按各自 fixture 运行，不将 404 项描述成 PostgreSQL 端到端或真实天气供应商联调。本轮未验证服务器部署或真实模型效果。

两个警告来自已有 Starlette/httpx TestClient 兼容提示和 `HTTP_422_UNPROCESSABLE_ENTITY` 名称弃用提示，不是测试失败。仓库的 11 月 20 日 RAG 原始报告未改写。
