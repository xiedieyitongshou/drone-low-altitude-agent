from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest
from psycopg.types.json import Json

from scripts.migrate_sqlite_to_postgres import convert_value, find_missing_user_ids


def test_convert_value_handles_json_boolean_and_datetime_columns() -> None:
    json_value = convert_value("raw_request_json", '{"location": "test-site"}')

    assert isinstance(json_value, Json)
    assert convert_value("allow_cruise", 1) is True
    assert convert_value("allow_cruise", 0) is False
    assert convert_value("created_at", "2026-09-01T08:00:00") == datetime(
        2026,
        9,
        1,
        8,
        0,
        0,
    )
    assert convert_value("location", "test-site") == "test-site"


def test_convert_value_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        convert_value("raw_request_json", "not-json")


def test_find_missing_user_ids_detects_orphan_references() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(
            """
            CREATE TABLE users (id TEXT PRIMARY KEY);
            CREATE TABLE user_profiles (user_id TEXT);
            CREATE TABLE conversation_records (user_id TEXT);
            CREATE TABLE session_records (user_id TEXT);
            CREATE TABLE mission_tasks (user_id TEXT);
            CREATE TABLE rule_sets (owner_user_id TEXT);
            CREATE TABLE knowledge_documents (user_id TEXT);
            CREATE TABLE knowledge_index_jobs (triggered_by_user_id TEXT);

            INSERT INTO users (id) VALUES ('existing-user');
            INSERT INTO user_profiles (user_id) VALUES ('existing-user');
            INSERT INTO user_profiles (user_id) VALUES ('missing-profile-user');
            INSERT INTO conversation_records (user_id) VALUES ('missing-conversation-user');
            INSERT INTO mission_tasks (user_id) VALUES (NULL);
            """
        )

        assert find_missing_user_ids(conn) == [
            "missing-conversation-user",
            "missing-profile-user",
        ]
    finally:
        conn.close()
