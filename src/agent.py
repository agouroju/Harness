"""The radar brain: explore ClickHouse with agent-written SQL, draft a cited
briefing, ground it in Senso, publish to cited.md."""

from datetime import datetime, timezone

from . import config, db, ingest, llm, senso

if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
    from langfuse import observe
else:  # tracing disabled — no-op decorator
    def observe(*args, **kwargs):
        def wrap(fn):
            return fn
        return wrap if not args else args[0]

ANALYST_SYSTEM = """You are an autonomous data analyst for the AI developer-tools ecosystem.
You write ClickHouse SQL to find genuinely interesting, *recent* signals: issue spikes,
hot Hacker News discussions, star growth, controversial releases. Prefer queries that
join activity to concrete titles and URLs so findings can be cited."""

SQL_PROMPT = """{schema}

Write 3 different ClickHouse SELECT queries to surface the most newsworthy signals from
the last {hours} hours. Rules:
- SELECT/WITH only, single statement each, always LIMIT <= 20
- Include url and title columns whenever possible (needed for citations)
- FINAL is NOT supported. Deduplicate ReplacingMergeTree tables with
  GROUP BY key columns + argMax(col, fetched_at) or max() aggregates

Respond as JSON: {{"queries": [{{"goal": "...", "sql": "..."}}, ...]}}"""

BRIEFING_PROMPT = """You are writing a published intelligence briefing for cited.md titled
"AI DevTool Radar — {date}". Audience: people building with AI developer tools.

Below are query results from a live database of GitHub activity and Hacker News
discussion from the last {hours} hours. Write a briefing in markdown:

- Open with a 2-3 sentence "what mattered today"
- 2-4 findings as short sections, each grounded in the data
- EVERY factual claim must cite its source inline as a markdown link using the URLs
  in the data. Never state anything not supported by the rows below.
- End with a one-line "Radar take".

Query results:
{results}

Respond as JSON: {{"seo_title": "...", "summary": "<one sentence>", "markdown": "..."}}"""


@observe(name="propose-sql")
def propose_queries() -> list[dict]:
    out = llm.complete_json(
        ANALYST_SYSTEM,
        SQL_PROMPT.format(schema=db.schema_description(), hours=config.RADAR_LOOKBACK_HOURS),
    )
    return out.get("queries", [])[:3]


@observe(name="run-sql")
def run_queries(ch, queries: list[dict]) -> list[dict]:
    findings = []
    for q in queries:
        try:
            cols, rows = db.run_select(ch, q["sql"])
            findings.append({"goal": q["goal"], "sql": q["sql"], "columns": cols, "rows": rows})
            print(f"  ✓ {q['goal']} — {len(rows)} rows")
        except Exception as err:
            print(f"  ✗ {q['goal']} — {err}")
    return findings


@observe(name="draft-briefing")
def draft_briefing(findings: list[dict]) -> dict:
    date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    rendered = []
    for f in findings:
        lines = [f"### Goal: {f['goal']}", f"Columns: {f['columns']}"]
        lines += [str(row) for row in f["rows"][:15]]
        rendered.append("\n".join(lines))
    return llm.complete_json(
        ANALYST_SYSTEM,
        BRIEFING_PROMPT.format(
            date=date, hours=config.RADAR_LOOKBACK_HOURS, results="\n\n".join(rendered)
        ),
    )


@observe(name="radar-run")
def run_once() -> dict:
    started = datetime.now(timezone.utc).isoformat()
    print(f"=== Radar run {started} ===")

    ch = db.client()
    db.init(ch)

    counts = ingest.run(ch)

    print("Agent proposing SQL...")
    queries = propose_queries()
    findings = run_queries(ch, queries)
    if not findings:
        print("No successful queries — aborting run")
        return {"published": False}

    print("Drafting cited briefing...")
    briefing = draft_briefing(findings)

    print("Grounding sources in Senso...")
    source_doc = "\n\n".join(
        f"## {f['goal']}\nSQL: `{f['sql']}`\nRows:\n"
        + "\n".join(str(r) for r in f["rows"][:15])
        for f in findings
    )
    senso.ingest_ground_truth(
        f"Radar ground truth — {started}",
        f"Ingest counts: {counts}\n\n{source_doc}",
    )

    print("Publishing to cited.md...")
    result = senso.publish_briefing(
        briefing["seo_title"], briefing["summary"], briefing["markdown"]
    )
    status = "PUBLISHED" if result["published"] else "saved as draft (publish rejected)"
    print(f"=== {status}: {briefing['seo_title']} ===")
    print(str(result["response"])[:800])
    return result
