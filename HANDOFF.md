# HANDOFF — AI DevTool Radar (Harness Engineering Hack)

State as of 2026-06-12 ~20:30 UTC. Repo: `github.com/agouroju/Harness`, working dir
`/Users/sidharthareddypotu/Aditya/engine`. **The project is WORKING END TO END.**

## What this is

Hackathon entry (Context Engineering Challenge): an autonomous agent that ingests
real-time GitHub + Hacker News data into ClickHouse, writes its own SQL to find
signals, grounds findings in Senso, and publishes cited briefings to cited.md,
fully traced in Langfuse. Judging: Autonomy, Idea, Technical Implementation,
Tool Use (3+ sponsor tools), 3-min demo. Sponsor tools in use: ClickHouse,
Senso/cited.md, Langfuse (+ Airbyte planned, see TODO).

## Proof it works

- **Live published article**: https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b
  (re-running updates the same day's article: `citeables_action: update`)
- Langfuse traces visible at us.cloud.langfuse.com, project `radar`
  (`/project/cmqbdlnol01tyad0dmu6xf51e/traces`) — shows agent-written SQL + LLM calls
- ClickHouse Cloud service `radar` (AWS us-east-1, host in `.env`) holds
  ~459 GitHub issues/PRs, ~36 HN stories, repo star snapshots

## Commands

```bash
cd /Users/sidharthareddypotu/Aditya/engine
uv run python -m src.main --check   # validate all connections
uv run python -m src.main --once    # one full run: ingest -> SQL -> publish
uv run python -m src.main --loop    # autonomous loop (RADAR_INTERVAL_MIN=60)
```

## Credentials — ALL in `.env` (gitignored), all working

ClickHouse (host/password), Senso (`tgr_` key + `SENSO_PUBLISHER_ID` pinned to
cited.md + `SENSO_QUESTION_ID` pinned), OpenAI key (borrowed from
`../hack/researchbrain/.env.local` ROCKETRIDE_OPENAI_KEY), Langfuse pk/sk
(US region), GitHub token (from `gh auth token`).

## Hard-won API knowledge (do not rediscover)

- **Senso API**: base `https://apiv2.senso.ai/api/v1`, header `X-API-Key`.
  Ingest: `POST /org/kb/raw {title, text}`. Publish: `POST /org/content-engine/publish
  {raw_markdown, seo_title, summary, geo_question_id, publisher_ids}`.
  `geo_question_id` is REQUIRED (auto-created via `POST /org/prompts
  {question_text, type:"awareness"}` — see `src/senso.py:ensure_question_id`).
  Destination activation has NO public endpoint and no UI toggle; it was unlocked via
  `PATCH /org/content-generation {enable_content_generation: true, publishers: [<id>]}`
  — already done for this org, cited.md publisher id `afa1052b-8226-438c-895e-335dcf21743a`.
- **ClickHouse Cloud**: SharedMergeTree does NOT support `FINAL` — the agent prompt
  tells the LLM to dedupe with GROUP BY + argMax. HTTP sessions don't persist `USE db`,
  so every table reference is fully qualified (`radar.hn_stories`).
- **Git identity**: anything under `/Aditya` commits as Aditya Gouroju and pushes
  via SSH key `/Aditya/id_aditya` (gitconfig includeIf). Remote must stay SSH
  (`git@github.com:agouroju/Harness.git`) — https pushes as sid-rp and gets 403.
- The user's shell rewrites some commands through `rtk` (token-saving proxy); if a
  CLI flag fails oddly, that's why.

## TODO (priority order)

1. **Airbyte** (4th sponsor tool, ~15 min): cloud.airbyte.com — GitHub source
   (repos in `src/config.py` TRACKED_REPOS) -> ClickHouse destination (creds from
   `.env`, database `radar`), hourly schedule. Then set `INGEST_MODE=airbyte` in
   `.env` (skips built-in ingester; tables are compatible by design).
2. **Demo prep**: rehearse 3-min script in README.md; keep one published article
   as backup; show Langfuse trace of agent-written SQL + the cited.md article.
3. **Devpost submission**: devpost.com entry exists (Harness Engineering Hack,
   submission 1049032) — needs writeup + repo link + demo video.
4. Optional: `--loop` running during judging for the autonomy story; x402 paywall
   mention as monetization next-step (do not build).

## File map

`src/config.py` env + tracked repos · `src/db.py` ClickHouse client/DDL/SELECT-guard
· `src/ingest.py` HN+GitHub direct ingest (Airbyte fallback) · `src/senso.py` Senso
client (ingest/draft/publish/question) · `src/llm.py` OpenAI-compatible client w/
Langfuse wrap · `src/agent.py` the run pipeline · `src/main.py` CLI entry.
