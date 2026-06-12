# AI DevTool Radar

**A fully autonomous AI analyst that watches the AI developer-tool ecosystem and publishes cited intelligence briefings — with no human in the loop.**

Built for the **Harness Engineering Hack — Context Engineering Challenge**.

🔴 **Live app:** https://ai-devtool-radar.onrender.com
📰 **Published briefing (real, live):** https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b

---

## The problem

The AI tooling ecosystem moves faster than anyone can read: model releases, breaking
changes, repo activity, HN debates. Human analysts are slow, expensive — and rarely cite
their sources. AI summaries hallucinate. Builders need a feed of *what actually happened,
with receipts*.

## What it does

The user's **only** input is *what to watch*: GitHub repositories and blog/news feeds
(defaults: OpenAI & Anthropic news, Google AI, DeepMind, Meta AI, Hugging Face, LangChain,
GitHub blog, Vercel, Simon Willison, Hacker News — plus 10 major AI-tooling repos).
Everything else is autonomous:

1. Every tracked source is a **real managed data pipeline** — adding a source in the web UI
   creates an Airbyte source + connection via API, syncing hourly into ClickHouse
2. On a schedule (and on demand), the agent **writes its own SQL** against the live data
   to hunt for signals: issue spikes, hot releases, provider announcements, HN debates
3. It **fetches the full source articles** (not just RSS snippets) and HN comment threads
   for the items it selected, so the briefing explains what actually happened
4. It drafts a briefing where **every claim carries an inline citation**, grounds the
   evidence in Senso's knowledge base, and **publishes to cited.md**
5. Every run is **fully traced** in Langfuse — you can inspect the exact SQL the agent
   chose to write, every prompt, and the cost (~$0.0002/run)

## Tech stack — what handles which part

| Layer | Technology | What it does here |
|---|---|---|
| **Ingestion** | **Airbyte** | ALL data movement: 1 GitHub source (10 repos → issues, PRs, stars) + 12 RSS pipelines, hourly incremental syncs into ClickHouse. Also the **control plane**: the app creates/deletes pipelines through Airbyte's API when users edit sources |
| **Storage + analysis** | **ClickHouse Cloud** | The agent's memory (~90k rows, live). The analysis engine: the agent's intelligence *is* the SQL it writes itself against this database |
| **Reasoning** | **OpenAI (gpt-4o-mini)** | Proposes the analytical SQL each run; drafts the cited briefing from results + full-article context |
| **Grounding + publishing** | **Senso → cited.md** | Each run's evidence is ingested into Senso's knowledge base as ground truth; the briefing publishes through Senso's content engine to the cited.md destination |
| **Observability** | **Langfuse** | One trace per run: prompts, agent-written SQL, article fetches, latency, cost |
| **Hosting** | **Render** | The full stack — web dashboard (frontend), API + 6-hour scheduler (backend) — runs as one Render web service |
| Glue | Python (stdlib) | Agent loop, dashboard, watchlist→Airbyte reconciler. No frameworks |

## Architecture

```
        user edits sources (web UI / tracked_repos.txt / tracked_feeds.txt)
                       │  reconciler (Airbyte API)
                       ▼
┌──────────────────────────────┐   hourly syncs   ┌─────────────────────────┐
│ AIRBYTE                      │ ───────────────► │ CLICKHOUSE              │
│ · GitHub: issues/PRs/stars   │                  │ radar + radar_airbyte   │
│ · 12 feeds: LLM provider     │                  │ (~90k rows, live)       │
│   blogs, AI sites, HN        │                  └───────────┬─────────────┘
└──────────────────────────────┘                              │ agent-written SQL
                                                              ▼
        ┌────────────┐  traces   ┌────────────────────────────────────────┐
        │ LANGFUSE   │ ◄──────── │ AGENT (Render, every 6h + on demand)   │
        │ every step │           │ SQL → findings → fetch full articles → │
        └────────────┘           │ cited draft → ground in Senso          │
                                 └───────────────────┬────────────────────┘
                                                     ▼
                                 ┌────────────────────────────────────────┐
                                 │ SENSO → CITED.MD                       │
                                 │ ground-truth KB + published briefing,  │
                                 │ every claim hyperlinked to its source  │
                                 └────────────────────────────────────────┘
```

## Judging criteria mapping

- **Autonomy** — two independent schedules (hourly Airbyte syncs + 6-hour analysis runs);
  zero human input from data to published article
- **Idea** — an analyst that never sleeps and always shows receipts; sources are
  user-configurable so it generalizes to any vertical
- **Technical implementation** — agent writes its own SQL; pipelines are created
  programmatically; publish path reverse-engineered to Senso's content engine; full
  tracing; SELECT-only SQL guard
- **Tool use** — five sponsor tools, each load-bearing (table above)
- **Monetization (next step)** — premium per-company deep-dives behind an **x402**
  paywall: other agents pay per request to read; cited.md is already agent-consumable

## Run it yourself

```bash
uv venv && uv pip install -r requirements.txt
cp .env.example .env                      # fill in keys (see comments)
uv run python -m src.main --check         # validate every connection
uv run python -m src.main --once          # one full autonomous run → cited.md
uv run python -m src.main --sync-sources  # make Airbyte match the watchlists
uv run python -m src.webapp               # the dashboard (what runs on Render)
```

Manage sources from the web UI, or:

```bash
uv run python -m src.main --add-feed https://blog.example.com/rss
uv run python -m src.main --add-repo vercel/ai
uv run python -m src.main --list-feeds / --list-repos
```

## Repo map

`src/agent.py` the brain · `src/pipelines.py` watchlist→Airbyte reconciler ·
`src/airbyte.py` Airbyte API client · `src/db.py` ClickHouse + SQL guard ·
`src/senso.py` Senso/cited.md client · `src/webapp.py` dashboard ·
`src/llm.py` LLM client (Langfuse-wrapped) · `tracked_repos.txt` / `tracked_feeds.txt`
the user-editable watchlists · `HANDOFF.md` full project handdown
