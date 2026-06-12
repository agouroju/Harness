"""Editable repository watchlist helpers."""

import re
from urllib.parse import urlparse

from . import config

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def normalize_repo(value: str) -> str:
    """Normalize GitHub repo input to owner/repo."""
    repo = value.strip()
    if not repo:
        raise ValueError("Repository cannot be empty")

    if repo.startswith("git@github.com:"):
        repo = repo.removeprefix("git@github.com:")
    elif "://" in repo:
        parsed = urlparse(repo)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            raise ValueError("Only GitHub repository URLs are supported")
        repo = parsed.path.lstrip("/")

    repo = repo.removesuffix(".git").strip("/")
    parts = repo.split("/")
    if len(parts) >= 2:
        repo = "/".join(parts[:2])

    if not REPO_RE.match(repo):
        raise ValueError("Repository must look like owner/repo or a GitHub repo URL")
    return repo


def read_repos() -> list[str]:
    """Return repos from the editable file, falling back to defaults."""
    return list(config.TRACKED_REPOS)


def write_repos(repos: list[str]) -> None:
    path = config.tracked_repos_path()
    lines = [
        "# AI DevTool Radar repository watchlist",
        "# One GitHub repo per line, in owner/repo format.",
        "",
    ]
    lines.extend(repos)
    lines.append("")
    path.write_text("\n".join(lines))


def add_repo(value: str) -> tuple[str, bool]:
    repo = normalize_repo(value)
    repos = read_repos()
    if repo.casefold() in {item.casefold() for item in repos}:
        return repo, False
    repos.append(repo)
    write_repos(repos)
    return repo, True


def remove_repo(value: str) -> tuple[str, bool]:
    repo = normalize_repo(value)
    repos = read_repos()
    kept = [item for item in repos if item.casefold() != repo.casefold()]
    if len(kept) == len(repos):
        return repo, False
    write_repos(kept)
    return repo, True


def normalize_feed(value: str) -> str:
    url = value.strip()
    if not url:
        raise ValueError("Feed URL cannot be empty")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Feed must be a full http(s) URL to an RSS/Atom feed")
    return url


def read_feeds() -> list[str]:
    return list(config.TRACKED_FEEDS)


def write_feeds(feeds: list[str]) -> None:
    path = config.tracked_feeds_path()
    lines = [
        "# AI DevTool Radar feed watchlist",
        "# One RSS/Atom feed URL per line (LLM provider blogs, AI tool sites, HN searches).",
        "",
    ]
    lines.extend(feeds)
    lines.append("")
    path.write_text("\n".join(lines))


def add_feed(value: str) -> tuple[str, bool]:
    feed = normalize_feed(value)
    feeds = read_feeds()
    if feed.casefold() in {item.casefold() for item in feeds}:
        return feed, False
    feeds.append(feed)
    write_feeds(feeds)
    return feed, True


def remove_feed(value: str) -> tuple[str, bool]:
    feed = normalize_feed(value)
    feeds = read_feeds()
    kept = [item for item in feeds if item.casefold() != feed.casefold()]
    if len(kept) == len(feeds):
        return feed, False
    write_feeds(kept)
    return feed, True
