# AI DevTool Radar

**An autonomous analyst that watches the AI developer-tool ecosystem and publishes cited intelligence briefings — with no human in the loop.**

Built for the Harness Engineering Hack (Context Engineering Challenge).

## What it does

Every run, the agent:

1. Pulls fresh, real-time data about AI dev tools (GitHub activity + Hacker News discussion) into **ClickHouse** — via **Airbyte** syncs (or the built-in direct ingester as fallback)
2. Reads the database schema and **writes its own SQL** to hunt for signals: issue spikes, release reactions, trending discussions
3. Grounds every finding in source rows/URLs ingested into **Senso** as ground truth
4. Drafts a briefing where every claim carries a citation and **publishes it to cited.md** via Senso's content engine
5. Traces the entire run — every SQL query it chose, every prompt — in **Langfuse**

## Architecture

```
┌─────────┐   sync    ┌────────────┐  agent-written SQL  ┌─────────┐
│ Airbyte │ ────────► │ ClickHouse │ ◄────────────────── │  Agent  │
│ (GitHub,│           │ (storage + │                     │ (loop)  │
│  HN/RSS)│           │  analysis) │                     └────┬────┘
└─────────┘           └────────────┘        ground truth +    │
                                            publish           ▼
                      ┌──────────┐   draft + publish   ┌────────────┐
                      │ Langfuse │ ◄─── traces ─────── │   Senso    │ ──► cited.md
                      │ (observe)│                     │ (context + │
                      └──────────┘                     │  publish)  │
                                                       └────────────┘
```

### Sponsor tools & their jobs (each one load-bearing)

| Tool | Job |
|---|---|
| **Airbyte** | Entire ingestion layer — managed connectors sync GitHub + HN/RSS into ClickHouse on a schedule |
| **ClickHouse** | Entire analysis engine — the agent writes SQL against it; aggregations ARE the intelligence |
| **Senso / cited.md** | Ground truth + the publishing pipeline (`kb/raw` → `engine/draft` → `engine/publish` → citeables) |
| **Langfuse** | Full observability — every run is one inspectable trace |

## Components

- `src/config.py` — env-driven settings (all credentials via `.env`)
- `src/db.py` — ClickHouse client, table DDL, safe query execution (SELECT-only guard)
- `src/ingest.py` — fallback/direct ingestion (HN Algolia API + GitHub REST) so the pipeline works even before Airbyte syncs are configured
- `src/senso.py` — Senso API client: ingest ground truth, draft, publish to cited.md
- `src/llm.py` — OpenAI-compatible LLM client (works with OpenAI/OpenRouter/any gateway), auto-wrapped with Langfuse tracing when keys are present
- `src/agent.py` — the radar brain: schema → SQL proposals → execution → findings → cited briefing → publish
- `src/main.py` — entry point: `--check` (validate env), `--once` (single run), `--loop` (autonomous schedule)

## Setup (hackathon speed-run)

```bash
uv venv && uv pip install -r requirements.txt
cp .env.example .env   # paste your keys
uv run python -m src.main --check
```

### Keys you need

1. **ClickHouse Cloud** — console.clickhouse.cloud → create service → copy host/password
2. **Senso** — docs.senso.ai → API key (`tgr_...`)
3. **LLM** — any OpenAI-compatible key (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`)
4. **Langfuse** (optional but worth it) — cloud.langfuse.com → project keys
5. **GitHub token** (optional, raises rate limits) — fine-grained PAT, public repo read

### Airbyte (primary ingestion)

In Airbyte Cloud: create **GitHub** source (track the repos in `config.py`) and a **ClickHouse** destination with the same credentials as `.env`, schedule hourly syncs. Until that's live, `INGEST_MODE=direct` (default) pulls the same data with the built-in ingester — same tables, same agent, zero code change (`INGEST_MODE=airbyte` skips the built-in pull).

## Run it

```bash
uv run python -m src.main --once    # one full autonomous run (ingest → analyze → publish)
uv run python -m src.main --loop    # run every RADAR_INTERVAL_MIN minutes, forever
```

## Demo script (3 min)

1. **(30s)** Problem: nobody can keep up with the AI tooling ecosystem; analysts are slow and don't cite sources
2. **(90s)** `python -m src.main --once` live: watch the Langfuse trace appear — the SQL the agent wrote itself, the findings, then the article landing on cited.md
3. **(60s)** Architecture slide + monetization: free daily briefing; deep-dive reports gated behind x402 so other agents can buy them programmatically

## Monetization (next step)

Premium per-company deep-dive reports behind an x402 paywall — agents pay per request to read; the publishing pipeline is already agent-consumable via cited.md.
