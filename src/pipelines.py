"""Reconcile the user's watchlists (repos + feeds) with Airbyte pipelines.

The two text files are the only thing a user edits:
  tracked_repos.txt  -> repositories inside the single Airbyte GitHub source
  tracked_feeds.txt  -> one Airbyte RSS source + connection per feed

`reconcile()` makes Airbyte match the files: creates missing RSS
sources/connections, deletes ones whose feed was removed, and replaces the
GitHub source's repository list. Each feed's stream lands in ClickHouse as
`radar_airbyte.<slug>__items`, which the agent discovers automatically.
"""

import re

from . import airbyte, config

RSS_NAME_PREFIX = "rss-"


def feed_slug(url: str) -> str:
    cleaned = re.sub(r"^https?://(www\.)?", "", url.strip().lower())
    cleaned = re.sub(r"\.(xml|rss|atom)([/?].*)?$", "", cleaned)
    slug = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return slug[:48]


def reconcile(trigger_new: bool = True) -> dict:
    """Make Airbyte sources/connections match the watchlist files."""
    report = {"created": [], "deleted": [], "github_repos": 0, "synced": []}

    sources = airbyte.list_sources()
    connections = airbyte.list_connections()
    conns_by_source = {}
    for conn in connections:
        conns_by_source.setdefault(conn.get("sourceId"), []).append(conn)

    wanted = {feed_slug(url): url for url in config.TRACKED_FEEDS}
    existing_rss = {
        src["name"].removeprefix(RSS_NAME_PREFIX): src
        for src in sources
        if src.get("name", "").startswith(RSS_NAME_PREFIX)
    }

    # Create sources + connections for new feeds
    for slug, url in wanted.items():
        if slug in existing_rss:
            continue
        src = airbyte.create_rss_source(f"{RSS_NAME_PREFIX}{slug}", url)
        source_id = src.get("sourceId")
        conn = airbyte.create_connection(source_id, f"{RSS_NAME_PREFIX}{slug}", f"{slug}__")
        report["created"].append(slug)
        if trigger_new and conn.get("connectionId"):
            try:
                airbyte.trigger_sync(conn["connectionId"])
                report["synced"].append(slug)
            except airbyte.AirbyteError as err:
                print(f"  ! sync trigger failed for {slug}: {err}")

    # Remove pipelines for feeds no longer tracked
    for slug, src in existing_rss.items():
        if slug in wanted:
            continue
        for conn in conns_by_source.get(src.get("sourceId"), []):
            airbyte.delete_connection(conn["connectionId"])
        airbyte.delete_source(src["sourceId"])
        report["deleted"].append(slug)

    # Keep the GitHub source's repository list in step with tracked_repos.txt
    if config.AIRBYTE_GITHUB_SOURCE_ID and config.GITHUB_TOKEN:
        airbyte.update_github_repositories(config.TRACKED_REPOS)
        report["github_repos"] = len(config.TRACKED_REPOS)

    return report
