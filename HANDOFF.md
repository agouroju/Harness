# AI DevTool Radar — Project Handdown

Updated 2026-06-12 ~22:50 UTC, minutes before demo. Repo: `github.com/agouroju/Harness`,
working dir `/Users/sidharthareddypotu/Aditya/engine`. Everything below is BUILT AND VERIFIED
unless marked otherwise.

## What the project is, and who it's for

**AI DevTool Radar is a fully autonomous analyst for the AI developer-tools ecosystem.**
The audience is anyone building with or betting on AI tooling (developers, founders,
investors) who can't keep up with the firehose of releases, debates, and repo activity.
Nobody operates it: the user's ONLY input is *what to watch* — a list of GitHub repos and
blog/news feeds. The radar syncs those sources hourly, writes its own SQL to find what's
newsworthy, and publishes a fully-cited intelligence briefing to cited.md on a schedule.

Built for the Harness Engineering Hack "Context Engineering Challenge": autonomous agent,
real action on the open web, grounded in ground-truth sources, 3+ sponsor tools,
published to cited.md.

## What each tech does (every one load-bearing)

| Tech | Role |
|---|---|
| **Airbyte** | ALL ingestion. One GitHub source (10 repos: issues/PRs/stars) + 8 RSS pipelines (OpenAI & Anthropic news mirrors, Google AI, Hugging Face, LangChain, Simon Willison, HN front page, HN AI-agent search), hourly syncs into ClickHouse. ALSO the control plane: the app creates/deletes pipelines through Airbyte's API when the user edits sources. |
| **ClickHouse** | Memory + analysis engine. Databases `radar` (agent-enriched HN context) and `radar_airbyte` (~90k issue rows + feed items). The agent's intelligence is SQL it writes itself against this data. |
| **OpenAI (gpt-4o-mini)** | The brain: proposes analytical SQL, drafts the cited briefing. |
| **Senso → cited.md** | Ground-truth knowledge base + publishing pipeline. Every run ingests its evidence into Senso, then publishes via content-engine to the cited.md destination. |
| **Langfuse** | Observability: every run is one trace — prompts, agent-written SQL, latency, cost (~$0.0002/run). Project `radar`, US region. |
| **Render** | Hosts the fullstack web app (frontend dashboard + backend + 6h scheduler), free tier. |
| **Python (stdlib http.server)** | The glue: agent loop, web dashboard, watchlist→Airbyte reconciler. |

## The full loop

tracked_repos.txt / tracked_feeds.txt (user edits, or web UI "Track a new source")
→ `pipelines.reconcile()` creates/deletes Airbyte sources+connections to match
→ Airbyte syncs everything hourly into ClickHouse
→ agent run (web "Sync & publish briefing" button, 6h scheduler, or `--once`):
  triggers all Airbyte syncs → LLM writes 3 SQL queries against the live schema
  (auto-discovers `radar_airbyte.*` tables) → executes (SELECT-only guard) →
  drafts briefing with inline citations → grounds evidence in Senso KB →
  publishes to cited.md → Langfuse traces it all.

## Live URLs (for the demo)

- **Published article**: https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b
- **Web app (Render)**: https://ai-devtool-radar.onrender.com (deploy started 22:46 UTC —
  verify it finished; free tier sleeps after idle, first hit takes ~50s)
- **Local web app**: `uv run python -m src.webapp` → http://localhost:8000
- **Langfuse traces**: us.cloud.langfuse.com → project radar → Tracing
- **Airbyte pipelines**: cloud.airbyte.com (9 connections, hourly)
- **Devpost entry**: submission 1049032, Harness Engineering Hack

## 3-minute demo script

1. (30s) Problem: the AI tooling ecosystem moves too fast; analysts are slow and uncited.
2. (60s) Web app: show tracked sources, add a feed live ("Start tracking" — point out it
   creates a real Airbyte pipeline automatically), press "Sync & publish briefing".
3. (60s) While it runs: Langfuse trace (the SQL the agent wrote ITSELF), Airbyte
   connections page (9 managed pipelines), ClickHouse row counts on the dashboard.
4. (30s) The payoff: the cited.md article — every claim hyperlinked. Monetization
   next-step: premium deep-dives behind x402 so other agents pay to read.

## Auth decision

Google OAuth deliberately skipped (consent screens + redirect URIs = not worth it at a
hackathon). Built-in HTTP Basic auth exists: set `WEB_USERNAME` + `WEB_PASSWORD` env vars
on Render to lock the dashboard. Currently OFF for frictionless demoing.

## Known limits / gotchas (tell the next agent)

- Render free tier: cold starts (~50s), and `tracked_*.txt` edits are EPHEMERAL on Render
  (lost on redeploy) — fine for demo; persistence would move the watchlist into ClickHouse.
- Senso publish needs `geo_question_id` (env pinned); destination activation was via
  undocumented `PATCH /org/content-generation` — already done, don't touch.
- ClickHouse Cloud: no `FINAL`, no session `USE`; all tables fully qualified.
- OpenAI/Anthropic block bot RSS — their feeds are Google News mirrors (`site:` queries).
- Git: inside /Aditya, commits author as agouroju; push via the SSH remote only.
- The user's shell proxies commands through `rtk`; weird CLI flag errors = use Read tool.
- GITHUB_TOKEN is a short-lived `gh` token — if Airbyte's GitHub source starts failing
  auth, mint a real PAT and update the source config (or rerun `--sync-sources` with a
  fresh token in .env).

## Commands

```bash
uv run python -m src.main --check         # validate every connection
uv run python -m src.main --once          # one autonomous run end-to-end
uv run python -m src.main --sync-sources  # reconcile Airbyte with watchlists
uv run python -m src.main --add-feed URL / --add-repo owner/repo / --list-feeds
uv run python -m src.webapp               # the dashboard (what's deployed on Render)
```
