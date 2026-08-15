# Knowledge Data

`advice_rules.json` is the original static knowledge library and is intentionally kept as a migration backup.

Day 128 migration status:

- Source JSON: `data/knowledge/advice_rules.json`
- Target table: `knowledge_documents`
- Import command: `python scripts/import_knowledge_json.py`
- Import behavior: upsert by `id`, set `review_status=approved`, `is_active=true`, and `index_dirty=true`
- Status: migrated successfully into the local default SQLite database on 2026-08-15; the JSON file is kept as a backup seed.

After the database migration is complete, application knowledge management should use the database as the source of truth. Keep this JSON file for rollback, audit, and repeatable seed import.
