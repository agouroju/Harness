"""Env-driven configuration for the AI DevTool Radar."""

import os

from dotenv import load_dotenv

load_dotenv()

# ClickHouse
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "")
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "radar")

# Senso
SENSO_API_KEY = os.getenv("SENSO_API_KEY", "")
SENSO_BASE_URL = os.getenv("SENSO_BASE_URL", "https://apiv2.senso.ai/api/v1")
SENSO_QUESTION_ID = os.getenv("SENSO_QUESTION_ID", "")

# LLM
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")

# GitHub (optional)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Radar behavior
INGEST_MODE = os.getenv("INGEST_MODE", "direct")
RADAR_INTERVAL_MIN = int(os.getenv("RADAR_INTERVAL_MIN", "60"))
RADAR_LOOKBACK_HOURS = int(os.getenv("RADAR_LOOKBACK_HOURS", "24"))

# What the radar watches
TRACKED_REPOS = [
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
    return [name for name, value in required.items() if not value]
