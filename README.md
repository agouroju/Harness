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

### Autonomy — acts on real-time data with no manual intervention

The radar runs on two independent clocks and needs nobody at the keyboard. Airbyte
syncs all 13 pipelines **every hour**, so ClickHouse always holds fresh, real-time
data. The Render scheduler then fires a full analysis run **every 6 hours**: it
triggers syncs, lets the agent explore the data, drafts the briefing, and publishes
to cited.md. From a new blog post appearing on openai.com to that post being analyzed
and cited in a published article, **no human touches anything** — the article at
cited.md is regenerated and updated throughout the day entirely on its own. Even the
data pipelines are self-managing: when a source is added or removed, the app
reconciles Airbyte to match without anyone opening the Airbyte UI.

### Idea — a real problem with real-world value

Every team building on AI tooling burns hours a week keeping up with model releases,
breaking changes, and ecosystem debates — or pays analysts who summarize slowly and
rarely cite sources. The radar is an analyst that never sleeps and always shows
receipts: every claim in every briefing links to the issue, post, or thread it came
from, so readers can verify rather than trust. Because the watchlist is the only
configuration, the same system generalizes beyond AI tooling to any vertical —
point it at fintech blogs and banking repos and it becomes a fintech analyst.

### Technical implementation — how it's built

The core design choice: **the agent's intelligence is SQL it writes itself.** Each
run, the LLM is shown the live database schema (including tables Airbyte created
minutes ago, discovered dynamically) and proposes its own analytical queries —
issue-spike detection, star-growth ranking, provider-news triage — executed behind a
SELECT-only guard. Selected findings are then *deepened*: the agent fetches the full
source articles and HN comment threads so it summarizes what actually happened, not
RSS snippets. Other implementation details judges may appreciate: Airbyte pipelines
are created/deleted programmatically through its API (token-minting client built from
scratch); the Senso publish path required reverse-engineering their CLI to find the
content-engine endpoints and an undocumented destination-activation call; ClickHouse
Cloud quirks (no `FINAL` on SharedMergeTree, stateless HTTP sessions) are handled
explicitly; and every run is one inspectable Langfuse trace showing the exact SQL the
agent chose, every prompt, and the cost (~$0.0002/run).

### Tool use — five sponsor tools, each one load-bearing

No tool here is a checkbox: remove any one and a whole layer disappears. **Airbyte**
is the entire ingestion layer *and* the control plane the app drives via API.
**ClickHouse** is the memory and the analysis engine the agent reasons against.
**Senso/cited.md** is both the ground-truth store and the publishing pipeline — the
hackathon's required output path. **Langfuse** is the observability layer that makes
an autonomous agent auditable. **Render** hosts the whole product — frontend
dashboard, backend API, and scheduler in one web service. (See the tech-stack table
above for exactly which part each handles.)

### Presentation — see it in 3 minutes

Open the [live app](https://ai-devtool-radar.onrender.com), add a feed and watch a
real Airbyte pipeline get created, press **Sync & publish briefing**, inspect the
agent's self-written SQL in Langfuse while it runs, then read the
[published, fully-cited article](https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b)
on cited.md.

### Monetization — the business model (next step)

The free daily briefing is the top of the funnel. Premium per-company deep-dive
reports go behind an **x402 paywall** so *other agents* can purchase and consume them
programmatically — cited.md is already an agent-readable endpoint, and the publishing
pipeline already supports multiple distinct articles per day, so the only missing
piece is the payment middleware.

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

## Future work

- **Better article summarization.** The briefing quality is good but not where we want
  it: the agent sometimes leans on engagement metrics instead of substance, and
  long-form sources deserve tighter synthesis. This is largely a **prompt-engineering
  problem** — refining the drafting prompt (section structure, cause-before-reaction
  ordering, stricter use of the full-article excerpts) and adding a critique/revise
  pass would noticeably raise the bar without any architecture changes.
- **x402 paywall** for premium per-company deep-dive reports (see Monetization above).
- **Persist watchlists in ClickHouse** instead of text files, so source edits survive
  redeploys on ephemeral hosting.

## Repo map

`src/agent.py` the brain · `src/pipelines.py` watchlist→Airbyte reconciler ·
`src/airbyte.py` Airbyte API client · `src/db.py` ClickHouse + SQL guard ·
`src/senso.py` Senso/cited.md client · `src/webapp.py` dashboard ·
`src/llm.py` LLM client (Langfuse-wrapped) · `tracked_repos.txt` / `tracked_feeds.txt`
the user-editable watchlists · `HANDOFF.md` full project handdown
