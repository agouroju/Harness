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

## Step 1 — Airbyte integration: ✅ DONE AND VERIFIED
(First sync succeeded: 11,727 rows in radar_airbyte.issues. Full --once run
afterwards published to cited.md successfully. Nothing left in this step.)

Already completed in Airbyte Cloud (account adityagouroju@gmail.com, workspace
062aea22-65cf-426e-a1f5-597497a3cbe7):
- Source "GitHub": PAT auth, 10 tracked repos, connection test passed
- Destination "ClickHouse": host from `.env`, port 8443, database `radar_airbyte`,
  connection test passed
- Connection "GitHub → ClickHouse" (id 086be19b-c436-4330-99a6-e04b7547478f):
  streams `issues` + `repositories` only, Every 1 hour, first sync STARTED
- Code already updated: `src/db.py schema_description(ch)` auto-discovers
  `radar_airbyte.*` tables and feeds them to the agent's SQL prompt

REMAINING VERIFICATION:
1. Check the sync succeeded: connection status page in Airbyte, or
   `uv run python -c "from src import db; print(db.client().query(\"SELECT table, sum(total_rows) FROM system.tables WHERE database='radar_airbyte' GROUP BY table\").result_rows)"`
2. If the first sync FAILED, open the connection's job log in Airbyte Cloud —
   most likely cause is ClickHouse permissions or the GitHub token (it used the
   short-lived `gh auth token` of the sid-rp account; replace with a fresh PAT
   in the source settings if expired).
3. After data lands, run `uv run python -m src.main --once` and confirm a
   Langfuse trace queries `radar_airbyte.*` (nudge SQL_PROMPT if needed).
4. Keep `INGEST_MODE=direct` — built-in ingester still supplies Hacker News,
   Airbyte supplies the GitHub firehose. Both is correct.

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
