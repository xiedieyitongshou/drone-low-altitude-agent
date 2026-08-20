# 文档导航

本目录承接根目录 `README.md` 中不适合展开的技术细节。根 README 负责项目定位、快速启动和演示入口；本目录负责架构、开发、部署、CI、权限、设计取舍和能力映射。

## 推荐阅读路径

1. 先看根目录 [README.md](../README.md)，快速理解项目定位和运行入口。
2. 再看 [架构设计说明.md](架构设计说明.md)，理解 Agent Runtime、Tool Calling、Trace、Guardrail、Hybrid RAG、任务单和前端展示的关系。
3. 需要运行项目时看 [本地开发与测试说明.md](本地开发与测试说明.md) 和 [Docker部署说明.md](Docker部署说明.md)。
4. 需要解释工程判断时看 [设计取舍说明.md](设计取舍说明.md) 和 [权限模型说明.md](权限模型说明.md)。
5. 准备展示或面试时看 [项目完成度与能力映射.md](项目完成度与能力映射.md)。

## 汇总型文档

| 文档 | 内容 |
|---|---|
| [架构设计说明.md](架构设计说明.md) | Agent Runtime、业务服务、Guardrail、Trace、RAG、任务单、前端展示关系 |
| [本地开发与测试说明.md](本地开发与测试说明.md) | 本地启动、依赖、环境变量、后端测试、前端构建、Eval 命令 |
| [Docker部署说明.md](Docker部署说明.md) | Docker Compose 服务、默认 Agent Loop、Redis 会话记忆、legacy fallback 边界 |
| [CI-CD说明.md](CI-CD说明.md) | GitHub Actions、快速 Eval 门禁、完整 Eval、服务器手动部署边界 |
| [设计取舍说明.md](设计取舍说明.md) | 规则引擎 vs LLM、RAG 边界、SQLite、Eval fast/full、前端权限边界 |
| [权限模型说明.md](权限模型说明.md) | `user_id`、`tenant_id`、`role`、`visibility` 在业务数据中的边界 |
| [项目完成度与能力映射.md](项目完成度与能力映射.md) | 功能模块、岗位能力、演示入口、测试文件和文档链接对应关系 |

## 关键专项文档

| 主题 | 文档 |
|---|---|
| 输入输出规范 | [Agent化输入输出规范.md](Agent化输入输出规范.md) |
| Tool Registry | [Day71-Tool-Registry设计.md](Day71-Tool-Registry设计.md) |
| Rule Planner | [Day72-Rule-Planner运行逻辑说明.md](Day72-Rule-Planner运行逻辑说明.md) |
| Agent State | [Day73-Agent-State结构与状态转换说明.md](Day73-Agent-State结构与状态转换说明.md) |
| Trace 闭环 | [Day83-Agent-Trace闭环说明.md](Day83-Agent-Trace闭环说明.md) |
| 自然语言入口 | [Day85-自然语言单入口业务路由设计.md](Day85-自然语言单入口业务路由设计.md) |
| 查询类工具化 | [Day86-查询类能力工具化说明.md](Day86-查询类能力工具化说明.md) |
| 多轮上下文 | [Day87-多轮追问与上下文合并说明.md](Day87-多轮追问与上下文合并说明.md) |
| 任务修改 | [Day88-任务修改与状态重算说明.md](Day88-任务修改与状态重算说明.md) |
| RAG 工具接入 | [Day89-RAG可选工具接入说明.md](Day89-RAG可选工具接入说明.md) |
| 混合编排验收 | [Day90-Day91-混合编排验收与演示说明.md](Day90-Day91-混合编排验收与演示说明.md) |
| Guardrail | [Day92-Guardrail架构设计.md](Day92-Guardrail架构设计.md) |
| 权限与工具边界 | [Day94-用户权限与工具调用边界.md](Day94-用户权限与工具调用边界.md) |
| RAG 架构 | [Day99-RAG检索架构重构.md](Day99-RAG检索架构重构.md) |
| BM25 召回 | [Day100-BM25关键词召回实现.md](Day100-BM25关键词召回实现.md) |
| Embedding 召回 | [Day101-Embedding向量召回实现.md](Day101-Embedding向量召回实现.md) |
| Hybrid Retrieval | [Day102-混合检索与Metadata加权.md](Day102-混合检索与Metadata加权.md) |
| Chunk 与 Rerank | [Day103-Chunk策略与Rerank.md](Day103-Chunk策略与Rerank.md) |
| RAG fallback | [Day104-RAG空召回低置信与QueryRewrite.md](Day104-RAG空召回低置信与QueryRewrite.md) |
| Eval 与 CI 预留 | [Day111-Eval接入测试体系与CI预留.md](Day111-Eval接入测试体系与CI预留.md) |
| 任务单状态流转 | [Day140-任务单接口与状态流转说明.md](Day140-任务单接口与状态流转说明.md) |
| 前端构建检查 | [Day143-前端构建与兼容检查.md](Day143-前端构建与兼容检查.md) |

## 维护原则

- 根 README 只放入口级摘要，不复制大段实现说明。
- 汇总型文档负责串联已有 Day 文档，不替代历史实现记录。
- 修改架构、部署、权限、Eval 行为时，同步更新对应汇总文档和根 README 链接。
- 避免同一段技术细节在多个文档中重复维护；需要展开时优先链接到专项文档。
