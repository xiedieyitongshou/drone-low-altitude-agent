from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Json
from sqlalchemy.engine import make_url


TABLES_IN_IMPORT_ORDER = [
    "locations",
    "users",
    "user_profiles",
    "mission_tasks",
    "task_requests",
    "weather_provider_snapshots",
    "weather_hourly_snapshots",
    "weather_warning_snapshots",
    "cruise_assessments",
    "cruise_hourly_assessments",
    "conversation_records",
    "session_records",
    "agent_trace_events",
    "rule_sets",
    "rule_items",
    "knowledge_documents",
    "knowledge_index_jobs",
]

JSON_COLUMNS = {
    "raw_request_json",
    "summary_risk_factors_json",
    "raw_payload_json",
    "risk_factors_json",
    "common_locations_json",
    "common_task_types_json",
    "parsed_json",
    "response_json",
    "last_context",
    "input_summary_json",
    "output_summary_json",
    "metadata_json",
    "validation_errors_json",
    "threshold_values_json",
    "rule_snapshot_json",
    "rule_hits_json",
    "task_types_json",
    "risk_tags_json",
    "warning_types_json",
    "warning_levels_json",
    "decision_scopes_json",
    "keywords_json",
    "candidate_locations_json",
    "selected_window_json",
    "profile_context_json",
}

BOOLEAN_COLUMNS = {
    "allow_cruise",
    "context_used",
    "success",
    "is_active",
    "is_default",
    "enabled",
    "index_dirty",
}

DATETIME_COLUMNS = {
    "created_at",
    "updated_at",
    "expires_at",
    "effective_at",
    "started_at",
    "finished_at",
}

SEQUENCES = {
    "locations": "locations_id_seq",
    "task_requests": "task_requests_id_seq",
    "cruise_assessments": "cruise_assessments_id_seq",
    "weather_provider_snapshots": "weather_provider_snapshots_id_seq",
    "weather_hourly_snapshots": "weather_hourly_snapshots_id_seq",
    "weather_warning_snapshots": "weather_warning_snapshots_id_seq",
    "cruise_hourly_assessments": "cruise_hourly_assessments_id_seq",
    "user_profiles": "user_profiles_id_seq",
    "conversation_records": "conversation_records_id_seq",
    "session_records": "session_records_id_seq",
    "agent_trace_events": "agent_trace_events_id_seq",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate SQLite data into PostgreSQL.")
    parser.add_argument("--sqlite-path", default="data/drone_agent.db")
    parser.add_argument(
        "--postgres-url",
        help="PostgreSQL connection URL. Defaults to the app's database configuration.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually truncate PostgreSQL tables and import data.",
    )
    return parser.parse_args()


def configured_postgres_url() -> str:
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.db.session import get_database_url

    url = make_url(get_database_url())
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Configure a PostgreSQL database or supply --postgres-url.")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [row[1] for row in rows]


def convert_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    if column in JSON_COLUMNS:
        if isinstance(value, str):
            return Json(json.loads(value))
        return Json(value)
    if column in BOOLEAN_COLUMNS:
        return bool(value)
    if column in DATETIME_COLUMNS and isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return value
    return value


def count_sqlite(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def count_postgres(conn: psycopg.Connection[Any], table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        return int(cur.fetchone()[0])


def find_missing_user_ids(sqlite_conn: sqlite3.Connection) -> list[str]:
    referenced_user_sql = """
        SELECT user_id FROM user_profiles WHERE user_id IS NOT NULL
        UNION
        SELECT user_id FROM conversation_records WHERE user_id IS NOT NULL
        UNION
        SELECT user_id FROM session_records WHERE user_id IS NOT NULL
        UNION
        SELECT user_id FROM mission_tasks WHERE user_id IS NOT NULL
        UNION
        SELECT owner_user_id FROM rule_sets WHERE owner_user_id IS NOT NULL
        UNION
        SELECT user_id FROM knowledge_documents WHERE user_id IS NOT NULL
        UNION
        SELECT triggered_by_user_id FROM knowledge_index_jobs WHERE triggered_by_user_id IS NOT NULL
    """
    existing_user_sql = 'SELECT id FROM users'
    referenced = {row[0] for row in sqlite_conn.execute(referenced_user_sql).fetchall()}
    existing = {row[0] for row in sqlite_conn.execute(existing_user_sql).fetchall()}
    return sorted(referenced - existing)


def insert_missing_users(
    conn: psycopg.Connection[Any],
    missing_user_ids: list[str],
) -> int:
    if not missing_user_ids:
        return 0
    now = datetime.utcnow()
    rows = [
        (
            user_id,
            user_id,
            "UNUSABLE_PASSWORD",
            user_id,
            "user",
            False,
            now,
            now,
        )
        for user_id in missing_user_ids
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO users (
                id, username, password_hash, display_name, role, is_active, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    return len(rows)


def truncate_postgres(conn: psycopg.Connection[Any]) -> None:
    table_list = ", ".join(f'"{table}"' for table in TABLES_IN_IMPORT_ORDER)
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")


def import_table(
    sqlite_conn: sqlite3.Connection,
    postgres_conn: psycopg.Connection[Any],
    table: str,
) -> int:
    columns = table_columns(sqlite_conn, table)
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute(f'SELECT * FROM "{table}"').fetchall()
    if not rows:
        return 0

    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    statement = f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'
    values = [
        tuple(convert_value(column, row[column]) for column in columns)
        for row in rows
    ]

    with postgres_conn.cursor() as cur:
        cur.executemany(statement, values)
    return len(values)


def reset_sequences(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        for table, sequence in SEQUENCES.items():
            cur.execute(
                f"""
                SELECT setval(
                    %s,
                    COALESCE((SELECT MAX(id) FROM "{table}"), 0) + 1,
                    false
                )
                """,
                (sequence,),
            )


def main() -> None:
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")
    if not args.yes:
        raise SystemExit("Refusing to modify PostgreSQL without --yes.")

    sqlite_conn = sqlite3.connect(sqlite_path.resolve().as_uri() + "?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    missing_tables = set(TABLES_IN_IMPORT_ORDER) - sqlite_tables(sqlite_conn)
    if missing_tables:
        raise SystemExit(f"SQLite database is missing tables: {sorted(missing_tables)}")

    with psycopg.connect(args.postgres_url or configured_postgres_url()) as postgres_conn:
        missing_user_ids = find_missing_user_ids(sqlite_conn)
        truncate_postgres(postgres_conn)
        imported_counts: dict[str, int] = {}
        for table in TABLES_IN_IMPORT_ORDER:
            imported_counts[table] = import_table(sqlite_conn, postgres_conn, table)
            if table == "users":
                imported_counts["users.synthetic_missing_fk"] = insert_missing_users(
                    postgres_conn,
                    missing_user_ids,
                )
        mismatches: list[str] = []
        for table in TABLES_IN_IMPORT_ORDER:
            sqlite_count = count_sqlite(sqlite_conn, table)
            postgres_count = count_postgres(postgres_conn, table)
            expected_count = sqlite_count
            if table == "users":
                expected_count += imported_counts["users.synthetic_missing_fk"]
            print(
                f"{table}: sqlite={sqlite_count}, postgres={postgres_count}, imported={imported_counts[table]}"
            )
            if expected_count != postgres_count:
                mismatches.append(table)
        if mismatches:
            raise SystemExit(f"Count mismatch after migration: {', '.join(mismatches)}")
        reset_sequences(postgres_conn)
        if missing_user_ids:
            print(
                f"Inactive users added for historical orphan references: {len(missing_user_ids)}"
            )

    sqlite_conn.close()
    print("SQLite to PostgreSQL migration completed successfully.")


if __name__ == "__main__":
    main()
