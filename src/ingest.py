"""Direct ingestion: Hacker News (Algolia API) + GitHub REST into ClickHouse.

This is the fallback path when Airbyte syncs aren't configured yet
(INGEST_MODE=direct). It writes to the same tables Airbyte targets,
so the agent is identical either way.
"""

import time
from datetime import datetime, timedelta, timezone
import html
import re

import requests

from . import config

HN_API = "https://hn.algolia.com/api/v1/search_by_date"
HN_ITEM_API = "https://hn.algolia.com/api/v1/items"
GH_API = "https://api.github.com"
HEADERS = {"User-Agent": "AI-DevTool-Radar/0.1 (+https://cited.md)"}


def _gh_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return headers


def _clean_comment_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<p\s*/?>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1200]


def _clean_page_text(value: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", value, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<noscript[\s\S]*?</noscript>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<(p|div|section|article|header|li|br|h[1-6])[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:config.HN_PAGE_TEXT_LIMIT]


def _page_title(value: str, fallback: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", value, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return fallback
    title = html.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
    return title[:300] or fallback


def _walk_comments(story_id: int, node: dict, rows: list[list], limit: int) -> None:
    if len(rows) >= limit:
        return
    if node.get("type") == "comment":
        text = _clean_comment_text(node.get("text") or "")
        if text:
            created_at_i = node.get("created_at_i")
            rows.append(
                [
                    story_id,
                    int(node["id"]),
                    node.get("author") or "",
                    text,
                    datetime.fromtimestamp(created_at_i, tz=timezone.utc).replace(tzinfo=None)
                    if created_at_i else datetime.now(timezone.utc).replace(tzinfo=None),
                ]
            )
    for child in node.get("children", []) or []:
        _walk_comments(story_id, child, rows, limit)
        if len(rows) >= limit:
            return


def ingest_hn_comments(ch, stories: list[dict]) -> int:
    """Fetch representative HN discussion text for the highest-signal stories."""
    comment_rows = []
    candidates = sorted(
        stories,
        key=lambda story: (story["num_comments"], story["points"]),
        reverse=True,
    )[:config.HN_COMMENT_STORY_LIMIT]

    for story in candidates:
        resp = requests.get(f"{HN_ITEM_API}/{story['id']}", timeout=30)
        if resp.status_code != 200:
            continue
        story_rows = []
        _walk_comments(story["id"], resp.json(), story_rows, config.HN_COMMENT_LIMIT)
        comment_rows.extend(story_rows)
        time.sleep(0.2)

    if comment_rows:
        ch.insert(
            f"{config.CLICKHOUSE_DATABASE}.hn_comments",
            comment_rows,
            column_names=["story_id", "id", "author", "text", "created_at"],
        )
    return len(comment_rows)


def ingest_hn_pages(ch, stories: list[dict]) -> int:
    """Fetch source-page excerpts so briefings can explain what triggered discussion."""
    page_rows = []
    candidates = sorted(
        stories,
        key=lambda story: (story["num_comments"], story["points"]),
        reverse=True,
    )[:config.HN_PAGE_STORY_LIMIT]

    for story in candidates:
        url = story["url"]
        if not url or url.startswith("https://news.ycombinator.com/"):
            continue
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
        except requests.RequestException:
            continue
        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or "text/html" not in content_type:
            continue
        text = _clean_page_text(resp.text)
        if len(text) < 200:
            continue
        page_rows.append([story["id"], url, _page_title(resp.text, story["title"]), text])
        time.sleep(0.2)

    if page_rows:
        ch.insert(
            f"{config.CLICKHOUSE_DATABASE}.hn_story_pages",
            page_rows,
            column_names=["story_id", "url", "title", "text"],
        )
    return len(page_rows)


def ingest_hn(ch) -> int:
    since = int((datetime.now(timezone.utc) - timedelta(hours=config.RADAR_LOOKBACK_HOURS)).timestamp())
    rows = []
    stories_by_id = {}
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
            story = {
                "id": int(hit["objectID"]),
                "title": hit.get("title") or "",
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "points": int(hit.get("points") or 0),
                "num_comments": int(hit.get("num_comments") or 0),
                "author": hit.get("author") or "",
                "created_at": datetime.fromtimestamp(hit["created_at_i"], tz=timezone.utc).replace(tzinfo=None),
            }
            stories_by_id[story["id"]] = story
            rows.append(
                [
                    story["id"],
                    story["title"],
                    story["url"],
                    story["points"],
                    story["num_comments"],
                    story["author"],
                    story["created_at"],
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
    page_count = ingest_hn_pages(ch, list(stories_by_id.values())) if stories_by_id else 0
    comment_count = ingest_hn_comments(ch, list(stories_by_id.values())) if stories_by_id else 0
    print(f"  {page_count} HN source pages captured for trigger summaries")
    print(f"  {comment_count} HN comments captured for discussion summaries")
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
