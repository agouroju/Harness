"""Direct ingestion: Hacker News (Algolia API) + GitHub REST into ClickHouse.

This is the fallback path when Airbyte syncs aren't configured yet
(INGEST_MODE=direct). It writes to the same tables Airbyte targets,
so the agent is identical either way.
"""

import time
from datetime import datetime, timedelta, timezone

import requests

from . import config

HN_API = "https://hn.algolia.com/api/v1/search_by_date"
GH_API = "https://api.github.com"


def _gh_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return headers


def ingest_hn(ch) -> int:
    since = int((datetime.now(timezone.utc) - timedelta(hours=config.RADAR_LOOKBACK_HOURS)).timestamp())
    rows = []
    for query in config.HN_QUERIES:
        resp = requests.get(
            HN_API,
            params={
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{since},points>5",
                "hitsPerPage": 50,
            },
            timeout=30,
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            rows.append(
                [
                    int(hit["objectID"]),
                    hit.get("title") or "",
                    hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    int(hit.get("points") or 0),
                    int(hit.get("num_comments") or 0),
                    hit.get("author") or "",
                    datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc).replace(tzinfo=None),
                    query,
                ]
            )
        time.sleep(0.3)
    if rows:
        ch.insert(
            f"{config.CLICKHOUSE_DATABASE}.hn_stories",
            rows,
            column_names=[
                "id", "title", "url", "points", "num_comments",
                "author", "created_at", "matched_query",
            ],
        )
    return len(rows)


def ingest_github(ch) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=config.RADAR_LOOKBACK_HOURS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    issue_rows, stat_rows = [], []
    for repo in config.TRACKED_REPOS:
        meta = requests.get(f"{GH_API}/repos/{repo}", headers=_gh_headers(), timeout=30)
        if meta.status_code != 200:
            print(f"  ! skipping {repo}: HTTP {meta.status_code}")
            continue
        m = meta.json()
        stat_rows.append([repo, m["stargazers_count"], m["forks_count"], m["open_issues_count"]])

        issues = requests.get(
            f"{GH_API}/repos/{repo}/issues",
            headers=_gh_headers(),
            params={"state": "all", "since": since, "per_page": 100, "sort": "updated"},
            timeout=30,
        )
        if issues.status_code != 200:
            continue
        for it in issues.json():
            issue_rows.append(
                [
                    repo,
                    int(it["number"]),
                    1 if "pull_request" in it else 0,
                    it.get("title") or "",
                    it.get("html_url") or "",
                    (it.get("user") or {}).get("login", ""),
                    it.get("state") or "",
                    int(it.get("comments") or 0),
                    datetime.strptime(it["created_at"], "%Y-%m-%dT%H:%M:%SZ"),
                    datetime.strptime(it["updated_at"], "%Y-%m-%dT%H:%M:%SZ"),
                ]
            )
        time.sleep(0.3)
    if issue_rows:
        ch.insert(
            f"{config.CLICKHOUSE_DATABASE}.github_issues",
            issue_rows,
            column_names=[
                "repo", "number", "is_pr", "title", "url",
                "author", "state", "comments", "created_at", "updated_at",
            ],
        )
    if stat_rows:
        ch.insert(
            f"{config.CLICKHOUSE_DATABASE}.github_repo_stats",
            stat_rows,
            column_names=["repo", "stars", "forks", "open_issues"],
        )
    return len(issue_rows)


def run(ch) -> dict:
    if config.INGEST_MODE == "airbyte":
        print("INGEST_MODE=airbyte — data arrives via Airbyte syncs, skipping direct pull")
        return {"hn": 0, "github": 0}
    print("Ingesting Hacker News...")
    hn = ingest_hn(ch)
    print(f"  {hn} stories")
    print("Ingesting GitHub...")
    gh = ingest_github(ch)
    print(f"  {gh} issues/PRs across {len(config.TRACKED_REPOS)} repos")
    return {"hn": hn, "github": gh}
