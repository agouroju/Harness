"""ClickHouse client, schema DDL, and guarded query execution."""

import clickhouse_connect

from . import config

DDL = [
    """
    CREATE TABLE IF NOT EXISTS {db}.hn_stories (
        id UInt64,
        title String,
        url String,
        points Int32,
        num_comments Int32,
        author String,
        created_at DateTime,
        matched_query String,
        fetched_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(fetched_at) ORDER BY id
    """,
    """
    CREATE TABLE IF NOT EXISTS {db}.github_issues (
        repo String,
        number UInt32,
        is_pr UInt8,
        title String,
        url String,
        author String,
        state String,
        comments Int32,
        created_at DateTime,
        updated_at DateTime,
        fetched_at DateTime DEFAULT now()
    ) ENGINE = ReplacingMergeTree(fetched_at) ORDER BY (repo, number)
    """,
    """
    CREATE TABLE IF NOT EXISTS {db}.github_repo_stats (
        repo String,
        stars UInt32,
        forks UInt32,
        open_issues UInt32,
        watched_at DateTime DEFAULT now()
    ) ENGINE = MergeTree ORDER BY (repo, watched_at)
    """,
]

SCHEMA_DESCRIPTION = """
Database: {db} (ClickHouse). Tables:

%RADAR%.hn_stories(id, title, url, points, num_comments, author, created_at DateTime, matched_query)
  -- Hacker News stories about AI dev tools. ReplacingMergeTree: use `FINAL` or max(fetched_at) dedup.

%RADAR%.github_issues(repo, number, is_pr UInt8, title, url, author, state, comments, created_at, updated_at)
  -- Issues AND pull requests (is_pr=1) for tracked AI tooling repos. ReplacingMergeTree: use `FINAL`.

%RADAR%.github_repo_stats(repo, stars, forks, open_issues, watched_at)
  -- Periodic star/fork snapshots per repo (append-only time series).
"""


def client():
    return clickhouse_connect.get_client(
        host=config.CLICKHOUSE_HOST,
        username=config.CLICKHOUSE_USER,
        password=config.CLICKHOUSE_PASSWORD,
        secure=True,
    )


def init(ch) -> None:
    ch.command(f"CREATE DATABASE IF NOT EXISTS {config.CLICKHOUSE_DATABASE}")
    for stmt in DDL:
        ch.command(stmt.format(db=config.CLICKHOUSE_DATABASE))


def schema_description() -> str:
    return SCHEMA_DESCRIPTION.replace("%RADAR%", config.CLICKHOUSE_DATABASE).format(db=config.CLICKHOUSE_DATABASE)


def run_select(ch, sql: str, max_rows: int = 50):
    """Execute agent-written SQL with a read-only guard. Returns (columns, rows)."""
    cleaned = sql.strip().rstrip(";")
    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError(f"Only SELECT queries are allowed, got: {cleaned[:60]!r}")
    if ";" in cleaned:
        raise ValueError("Multiple statements are not allowed")
    result = ch.query(cleaned, settings={"max_result_rows": max_rows + 1, "readonly": 1})
    return result.column_names, result.result_rows[:max_rows]
