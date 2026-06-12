# ORCHESTRATION GUIDE — for the next AI agent (Codex/other)

You are continuing a WORKING hackathon project. Read `HANDOFF.md` first for full
context. This file is your exact task list. Work from
`/Users/sidharthareddypotu/Aditya/engine`. Do not refactor working code.

## Step 0 — Verify nothing is broken (2 min)

```bash
cd /Users/sidharthareddypotu/Aditya/engine
uv run python -m src.main --check    # expect all ✓ (Langfuse line included)
```

If a ✓ turns into ✗, fix ONLY that connection (creds are in `.env`) before anything else.

## Step 1 — Airbyte integration (the ONLY missing sponsor tool)

Goal: replace the built-in ingester with an Airbyte Cloud sync. The ClickHouse
tables were designed so this is config-only — no code changes.

1. Go to https://cloud.airbyte.com (user may need to sign up — free trial, use
   Google login with adityagouroju@gmail.com to match other accounts).
2. **Source**: GitHub. Authenticate via OAuth (user clicks) or a PAT
   (`gh auth token` in terminal gives one). Repositories: copy the list from
   `src/config.py` `TRACKED_REPOS`. Streams needed: `issues` (and `repositories`
   if available). Sync window: last 30 days is plenty.
3. **Destination**: ClickHouse.
   - Host: `CLICKHOUSE_HOST` from `.env` (no https://)
   - Port: `8443`, SSL: enabled
   - Database: `radar_airbyte`  ← use a SEPARATE database so Airbyte's own
     table naming doesn't clash with the handwritten tables
   - User `default`, password from `.env`
4. **Connection**: source → destination, schedule "Every hour", start first sync.
5. While sync runs, add the Airbyte tables to the agent's view of the world:
   in `src/db.py` `SCHEMA_DESCRIPTION`, append a short paragraph describing the
   `radar_airbyte.*` tables (inspect actual names/columns after sync with
   `SHOW TABLES FROM radar_airbyte` via a quick `uv run python -c` script using
   `src.db.client()`). The agent's SQL will then use BOTH data sources.
6. Do NOT set `INGEST_MODE=airbyte` unless the Airbyte sync demonstrably contains
   fresh HN-equivalent data — the built-in ingester also feeds `hn_stories`,
   which Airbyte's GitHub source cannot. Keeping both is fine and honest:
   Airbyte = GitHub firehose, built-in = HN. Update README/HANDOFF wording accordingly.
7. Verify end-to-end: `uv run python -m src.main --once` → article updates on
   cited.md; check the Langfuse trace mentions a query against `radar_airbyte.*`
   (may need a run or two since the LLM chooses its own queries — you can nudge by
   adding "prefer at least one query against radar_airbyte tables" to SQL_PROMPT).
8. Commit + push (identity auto-switches to agouroju inside /Aditya; remote is SSH).

Fallback if Airbyte signup/trial blocks (no card, region issues, time): SKIP IT.
The project already satisfies "3+ sponsor tools" (ClickHouse, Senso/cited.md,
Langfuse). Update the pitch to say Airbyte is the planned scale-out ingestion path.

## Step 2 — Demo readiness (do not skip)

1. Run `uv run python -m src.main --loop` in a terminal and LEAVE IT RUNNING
   (this is the autonomy proof during judging).
2. Open and bookmark three tabs for the demo:
   - https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b (live article)
   - Langfuse traces: https://us.cloud.langfuse.com/project/cmqbdlnol01tyad0dmu6xf51e/traces
   - ClickHouse console showing `SELECT count() FROM radar.github_issues`
3. 3-minute script (also in README): 30s problem → 90s live run + Langfuse trace +
   article appearing → 60s architecture + "x402 paywall is the monetization
   next-step" (mention only, do not build).

## Step 3 — Devpost submission

Entry already exists: Harness Engineering Hack, submission 1049032
(devpost.com → user is signed in via browser). Needs: project name "AI DevTool
Radar", description (compress HANDOFF.md "What this is" + "Proof it works"),
repo link `github.com/agouroju/Harness`, the cited.md article link, sponsor
tools used list, and a demo video if required by the form.

## Environment quirks (will bite you if ignored)

- Shell proxies some commands through `rtk`; if grep/CLI flags behave oddly, use
  file Read tools or `command grep`.
- Git: inside /Aditya commits author as "Aditya Gouroju", push only via the
  existing SSH remote. NEVER switch remote to https.
- ClickHouse Cloud: no `FINAL`, no session `USE` — always fully-qualify tables.
- Senso: publish body REQUIRES geo_question_id (env `SENSO_QUESTION_ID` is set);
  destination already activated — do not touch `PATCH /org/content-generation`.
- Secrets live in `.env` only (gitignored). Never commit them, never print full
  keys into chat/logs.
- Playwright MCP attaches to the user's real Edge Beta browser (token already
  configured) — use it for any web-UI setup; their logins are live.
