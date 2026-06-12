"""ClickHouse-backed state for the web dashboard."""

import json
import uuid
from datetime import datetime, timezone

from . import config, db


SOURCE_DDL = """
CREATE TABLE IF NOT EXISTS {db}.watch_sources (
    id String,
    source_type LowCardinality(String),
    name String,
    locator String,
    airbyte_connection_id String,
    enabled UInt8,
    created_at DateTime DEFAULT now(),
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at) ORDER BY id
"""

RUN_DDL = """
CREATE TABLE IF NOT EXISTS {db}.radar_runs (
    id String,
    trigger String,
    status LowCardinality(String),
    message String,
    article_url String,
    airbyte_jobs String,
    started_at DateTime,
    finished_at DateTime
) ENGINE = ReplacingMergeTree(finished_at) ORDER BY id
"""


def init(ch=None) -> None:
    ch = ch or db.client()
    db.init(ch)
    ch.command(SOURCE_DDL.format(db=config.CLICKHOUSE_DATABASE))
    ch.command(RUN_DDL.format(db=config.CLICKHOUSE_DATABASE))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def add_source(source_type: str, name: str, locator: str, connection_id: str) -> str:
    ch = db.client()
    init(ch)
    source_id = str(uuid.uuid4())
    now = _now()
    ch.insert(
        f"{config.CLICKHOUSE_DATABASE}.watch_sources",
        [[source_id, source_type, name, locator, connection_id, 1, now, now]],
        column_names=[
            "id", "source_type", "name", "locator", "airbyte_connection_id",
            "enabled", "created_at", "updated_at",
        ],
    )
    return source_id


def set_source_enabled(source_id: str, enabled: bool) -> None:
    source = get_source(source_id)
    if not source:
        return
    ch = db.client()
    ch.insert(
        f"{config.CLICKHOUSE_DATABASE}.watch_sources",
        [[
            source["id"], source["source_type"], source["name"], source["locator"],
            source["airbyte_connection_id"], 1 if enabled else 0,
            source["created_at"], _now(),
        ]],
        column_names=[
            "id", "source_type", "name", "locator", "airbyte_connection_id",
            "enabled", "created_at", "updated_at",
        ],
    )


def list_sources(enabled_only: bool = False) -> list[dict]:
    ch = db.client()
    init(ch)
    where = "WHERE enabled = 1" if enabled_only else ""
    rows = ch.query(
        f"""
        SELECT id, source_type, name, locator, airbyte_connection_id, enabled, created_at, updated_at
        FROM (
            SELECT
                id,
                argMax(source_type, version_at) AS source_type,
                argMax(name, version_at) AS name,
                argMax(locator, version_at) AS locator,
                argMax(airbyte_connection_id, version_at) AS airbyte_connection_id,
                argMax(enabled, version_at) AS enabled,
                min(created_at) AS created_at,
                max(version_at) AS updated_at
            FROM (
                SELECT *, updated_at AS version_at
                FROM {config.CLICKHOUSE_DATABASE}.watch_sources
            )
            GROUP BY id
        )
        {where}
        ORDER BY updated_at DESC
        """,
    ).result_rows
    return [
        {
            "id": row[0],
            "source_type": row[1],
            "name": row[2],
            "locator": row[3],
            "airbyte_connection_id": row[4],
            "enabled": bool(row[5]),
            "created_at": row[6],
            "updated_at": row[7],
        }
        for row in rows
    ]


def get_source(source_id: str) -> dict | None:
    for source in list_sources():
        if source["id"] == source_id:
            return source
    return None


def start_run(trigger: str) -> str:
    ch = db.client()
    init(ch)
    run_id = str(uuid.uuid4())
    now = _now()
    ch.insert(
        f"{config.CLICKHOUSE_DATABASE}.radar_runs",
        [[run_id, trigger, "running", "", "", "[]", now, now]],
        column_names=[
            "id", "trigger", "status", "message", "article_url",
            "airbyte_jobs", "started_at", "finished_at",
        ],
    )
    return run_id


def finish_run(run_id: str, status: str, message: str, article_url: str = "", jobs: list | None = None) -> None:
    current = get_run(run_id)
    started = current["started_at"] if current else _now()
    ch = db.client()
    ch.insert(
        f"{config.CLICKHOUSE_DATABASE}.radar_runs",
        [[
            run_id,
            current["trigger"] if current else "unknown",
            status,
            message[:2000],
            article_url,
            json.dumps(jobs or []),
            started,
            _now(),
        ]],
        column_names=[
            "id", "trigger", "status", "message", "article_url",
            "airbyte_jobs", "started_at", "finished_at",
        ],
    )


def list_runs(limit: int = 20) -> list[dict]:
    ch = db.client()
    init(ch)
    rows = ch.query(
        f"""
        SELECT id, trigger, status, message, article_url, airbyte_jobs, started_at, finished_at
        FROM (
            SELECT
                id,
                argMax(trigger, version_at) AS trigger,
                argMax(status, version_at) AS status,
                argMax(message, version_at) AS message,
                argMax(article_url, version_at) AS article_url,
                argMax(airbyte_jobs, version_at) AS airbyte_jobs,
                min(started_at) AS started_at,
                max(version_at) AS finished_at
            FROM (
                SELECT *, finished_at AS version_at
                FROM {config.CLICKHOUSE_DATABASE}.radar_runs
            )
            GROUP BY id
        )
        ORDER BY finished_at DESC
        LIMIT {int(limit)}
        """,
    ).result_rows
    return [
        {
            "id": row[0],
            "trigger": row[1],
            "status": row[2],
            "message": row[3],
            "article_url": row[4],
            "airbyte_jobs": row[5],
            "started_at": row[6],
            "finished_at": row[7],
        }
        for row in rows
    ]


def get_run(run_id: str) -> dict | None:
    for run in list_runs(limit=100):
        if run["id"] == run_id:
            return run
    return None
