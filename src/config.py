"""Env-driven configuration for the AI DevTool Radar."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[1]

# ClickHouse
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "radar")

# Senso
SENSO_API_KEY = os.getenv("SENSO_API_KEY", "")
SENSO_BASE_URL = os.getenv("SENSO_BASE_URL", "https://apiv2.senso.ai/api/v1")
SENSO_QUESTION_ID = os.getenv("SENSO_QUESTION_ID", "")
SENSO_PUBLISHER_ID = os.getenv("SENSO_PUBLISHER_ID", "")

# LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")

# GitHub (optional)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Airbyte
AIRBYTE_API_URL = os.getenv("AIRBYTE_API_URL", "https://api.airbyte.com/v1").rstrip("/")
AIRBYTE_API_TOKEN = os.getenv("AIRBYTE_API_TOKEN", "")
AIRBYTE_CLIENT_ID = os.getenv("AIRBYTE_CLIENT_ID", "")
AIRBYTE_CLIENT_SECRET = os.getenv("AIRBYTE_CLIENT_SECRET", "")
AIRBYTE_WORKSPACE_ID = os.getenv("AIRBYTE_WORKSPACE_ID", "")
AIRBYTE_DESTINATION_ID = os.getenv("AIRBYTE_DESTINATION_ID", "")
AIRBYTE_GITHUB_SOURCE_ID = os.getenv("AIRBYTE_GITHUB_SOURCE_ID", "")
AIRBYTE_SYNC_WAIT_SECONDS = int(os.getenv("AIRBYTE_SYNC_WAIT_SECONDS", "120"))

# Radar behavior
INGEST_MODE = os.getenv("INGEST_MODE", "airbyte")
RADAR_INTERVAL_MIN = int(os.getenv("RADAR_INTERVAL_MIN", "60"))
RADAR_LOOKBACK_HOURS = int(os.getenv("RADAR_LOOKBACK_HOURS", "24"))
TRACKED_REPOS_FILE = os.getenv("TRACKED_REPOS_FILE", "tracked_repos.txt")
HN_COMMENT_STORY_LIMIT = int(os.getenv("HN_COMMENT_STORY_LIMIT", "8"))
HN_COMMENT_LIMIT = int(os.getenv("HN_COMMENT_LIMIT", "30"))
HN_PAGE_STORY_LIMIT = int(os.getenv("HN_PAGE_STORY_LIMIT", "8"))
HN_PAGE_TEXT_LIMIT = int(os.getenv("HN_PAGE_TEXT_LIMIT", "5000"))

# Web app
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("PORT", os.getenv("WEB_PORT", "8000")))
WEB_RUN_INTERVAL_HOURS = float(os.getenv("WEB_RUN_INTERVAL_HOURS", "6"))
WEB_SCHEDULER_ENABLED = os.getenv("WEB_SCHEDULER_ENABLED", "true").lower() not in {
    "0", "false", "no", "off"
}
WEB_USERNAME = os.getenv("WEB_USERNAME", "")
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")

# What the radar watches
DEFAULT_TRACKED_REPOS = [
    "anthropics/claude-code",
    "openai/codex",
    "langchain-ai/langchain",
    "ComposioHQ/composio",
    "modelcontextprotocol/servers",
    "langfuse/langfuse",
    "crewAIInc/crewAI",
    "browser-use/browser-use",
    "All-Hands-AI/OpenHands",
    "thesysdev/openui",
]


def tracked_repos_path() -> Path:
    """Path to the editable repository watchlist."""
    path = Path(TRACKED_REPOS_FILE).expanduser()
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def _load_tracked_repos() -> list[str]:
    """Load repos from file, with optional env additions."""
    path = tracked_repos_path()
    if path.exists():
        repos = []
        for raw in path.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                repos.append(line)
    else:
        repos = list(DEFAULT_TRACKED_REPOS)

    extra = os.getenv("TRACKED_REPOS", "")
    if extra:
        repos.extend(repo.strip() for repo in extra.replace(",", " ").split())

    deduped = []
    seen = set()
    for repo in repos:
        key = repo.casefold()
        if key not in seen:
            deduped.append(repo)
            seen.add(key)
    return deduped


TRACKED_REPOS = _load_tracked_repos()

# RSS/Atom feeds the radar watches (synced via Airbyte's RSS connector).
TRACKED_FEEDS_FILE = os.getenv("TRACKED_FEEDS_FILE", "tracked_feeds.txt")

DEFAULT_TRACKED_FEEDS = [
    "https://openai.com/news/rss.xml",            # OpenAI blog/news
    "https://rsshub.app/anthropic/news",          # Anthropic news (RSS mirror; no official feed)
    "https://blog.google/technology/ai/rss/",     # Google AI blog
    "https://huggingface.co/blog/feed.xml",       # Hugging Face blog
    "https://blog.langchain.dev/rss/",            # LangChain blog
    "https://simonwillison.net/atom/everything/", # Top AI-tools analysis
    "https://hnrss.org/frontpage?points=50",      # Hacker News front page (50+ points)
    "https://hnrss.org/newest?q=AI+agent&points=20",  # HN: AI agent stories
]


def tracked_feeds_path() -> Path:
    path = Path(TRACKED_FEEDS_FILE).expanduser()
    if path.is_absolute():
        return path
    return ROOT_DIR / path


def _load_tracked_feeds() -> list[str]:
    path = tracked_feeds_path()
    if path.exists():
        feeds = []
        for raw in path.read_text().splitlines():
            line = raw.split("#", 1)[0].strip()
            if line:
                feeds.append(line)
    else:
        feeds = list(DEFAULT_TRACKED_FEEDS)
    deduped = []
    seen = set()
    for feed in feeds:
        key = feed.casefold()
        if key not in seen:
            deduped.append(feed)
            seen.add(key)
    return deduped


TRACKED_FEEDS = _load_tracked_feeds()

HN_QUERIES = [
    "AI agent",
    "MCP",
    "Claude",
    "LLM tool",
    "coding assistant",
]


def missing_required() -> list[str]:
    """Names of required env vars that are not set."""
    required = {
        "CLICKHOUSE_HOST": CLICKHOUSE_HOST,
        "CLICKHOUSE_PASSWORD": CLICKHOUSE_PASSWORD,
        "SENSO_API_KEY": SENSO_API_KEY,
        "OPENAI_API_KEY": OPENAI_API_KEY,
    }
    def is_placeholder(v: str) -> bool:
        return not v or "..." in v or v.startswith("xxxxx")

    return [name for name, value in required.items() if is_placeholder(value)]
