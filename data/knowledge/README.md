# Knowledge Data

`advice_rules.json` is the original static knowledge library and is intentionally kept as a migration backup.

Day 128 migration status:

- Source JSON: `data/knowledge/advice_rules.json`
- Target table: `knowledge_documents`
- Import command: `python scripts/import_knowledge_json.py`
- Import behavior: upsert by `id`, set `review_status=approved`, `is_active=true`, and `index_dirty=true`
- Status: migrated successfully into the local default SQLite database on 2026-08-15; the JSON file is kept as a backup seed.

After the database migration is complete, application knowledge management should use the database as the source of truth. Keep this JSON file for rollback, audit, and repeatable seed import.

## 当前 RAG 知识来源与评测边界

同步日期：2026-11-22；依据 11 月 20 日 RAG 重构及当日原始验收，不重新运行。

运行时 `get_default_knowledge_path()` 依次选择：

1. 显式 `KNOWLEDGE_SOURCE_PATH`。
2. 已存在的数据库导出 `data/knowledge/index/knowledge_documents_source.json`。
3. 显式 `ADVICE_KNOWLEDGE_PATH`。
4. 仓库种子 `data/knowledge/advice_rules.json`。

因此，修改种子文件不等于已经更新运行中数据库或数据库导出的索引源。数据库内容仍应通过现有知识管理和索引重建流程维护。

自动 `scripts/rag_eval.py` 固定读取仓库种子，与 `evals/rag/fixtures.json` 的 3 条合成夹具合并，在临时目录建立各检索器索引；不写回数据库，不改运行索引。合成夹具分别验证 FAQ、私有授权和未生效知识，不能作为项目已有真实知识或在线用户数据统计。

11 月 20 日的原有语料 Agent 回放另行保存了语料哈希：有答案 Top-3 命中 6/6、无答案正确兜底 2/2。自动 Eval 与该回放分别报告。[当前 RAG 说明](../../docs/RAG检索与无答案处理说明.md) · [原始证据](../../docs/evidence/rag-applicability-20261120/README.md)
