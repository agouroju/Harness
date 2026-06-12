"""The radar brain: explore ClickHouse with agent-written SQL, draft a cited
briefing, ground it in Senso, publish to cited.md."""

from datetime import datetime, timezone
from html import unescape as html_unescape

import requests

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
join activity to concrete titles and URLs so findings can be cited. Popularity metrics
are ranking signals, not the story; the story is what happened, why it matters, and
what builders should do next."""

SQL_PROMPT = """{schema}

Write 3 different ClickHouse SELECT queries to surface the most newsworthy signals from
the last {hours} hours. Rules:
- At least one query MUST target the radar_airbyte feed tables (names ending in
  `__items`) — these hold new blog/news posts from LLM providers (OpenAI, Anthropic,
  Google, Hugging Face, etc). Select link, title, published, description; filter on
  published >= now() - INTERVAL {hours} HOUR
- SELECT/WITH only, single statement each, always LIMIT <= 20
- Include url and title columns whenever possible (needed for citations)
- Only select columns that exist in the schema. If a table lacks url/title, derive
  them from available fields, such as repo AS title and concat('https://github.com/', repo) AS url.
- For Hacker News stories, include the story id so discussion comments can be summarized
- FINAL is NOT supported. Deduplicate ReplacingMergeTree tables with
  GROUP BY key columns + argMax(col, fetched_at) or max() aggregates

Respond as JSON: {{"queries": [{{"goal": "...", "sql": "..."}}, ...]}}"""

BRIEFING_PROMPT = """You are writing a published intelligence briefing for cited.md titled
"AI DevTool Radar — {date}". Audience: people building with AI developer tools.

Below are query results from a live database of GitHub activity and Hacker News
discussion from the last {hours} hours, plus selected source-page and HN discussion context.
Write a briefing in markdown:

- Open with a 2-3 sentence "what mattered today"
- 2-3 findings as short sections, each grounded in the data and written as useful analysis
- Every section must have a heading plus 2-4 complete sentences. Do not include a
  heading if you cannot write a complete, sourced explanation under it.
- Every finding must first answer: what happened, who/what caused it, and why people
  noticed. The first sentence of each section should name the concrete trigger.
  Put the trigger before the reaction. Then explain the debate or implications.
- Do NOT make points/comment counts the finding. Use popularity metrics only to justify
  why an item was selected. Summarize the actual issue, project change, risk, or lesson.
- Avoid sentences like "this gained X points and Y comments"; write the engineering
  takeaway instead, for example "the debate centered on runaway agent costs, missing
  spend controls, and whether autonomous scanners need hard budget governors."
- For HN-driven findings, synthesize what the article/story is about and the substantive
  trigger from the supplied source-page excerpt before summarizing comments. Do not quote
  comments; paraphrase the consensus, disagreements, and engineering implications.
- Prefer concrete cause-and-effect wording: "The debate started because..." or
  "The trigger was..." when the source context supports it.
- If commenters focus on token burn, unexpected autonomy, security boundaries, spend,
  or loss of control, connect that concern back to the triggering behavior instead of
  presenting it as generic AI skepticism.
- EVERY factual claim must cite its source inline as a markdown link using the URLs
  in the data. Never state anything not supported by the rows below.
- End with a one-line "Radar take". Do not end on an unfinished heading or fragment.

Query results:
{results}

Source-page and HN discussion context:
{discussion}

Respond as JSON: {{"seo_title": "...", "summary": "<one sentence>", "markdown": "..."}}"""


@observe(name="propose-sql")
def propose_queries(ch) -> list[dict]:
    out = llm.complete_json(
        ANALYST_SYSTEM,
        SQL_PROMPT.format(schema=db.schema_description(ch), hours=config.RADAR_LOOKBACK_HOURS),
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


def _hn_story_ids(findings: list[dict]) -> list[int]:
    ids = []
    seen = set()
    for finding in findings:
        goal = finding.get("goal", "").lower()
        if "hacker news" not in goal and "hn" not in goal:
            continue
        columns = [str(col).lower() for col in finding["columns"]]
        id_index = None
        for candidate in ("story_id", "id"):
            if candidate in columns:
                id_index = columns.index(candidate)
                break
        if id_index is None:
            continue
        for row in finding["rows"]:
            try:
                story_id = int(row[id_index])
            except (TypeError, ValueError, IndexError):
                continue
            if story_id not in seen:
                ids.append(story_id)
                seen.add(story_id)
    return ids[:5]


def _comment_priority(text: str) -> int:
    lowered = text.lower()
    keywords = (
        "token",
        "cost",
        "security",
        "permission",
        "browser",
        "screenshot",
        "autonomous",
        "runaway",
        "spent",
        "expensive",
        "risk",
        "control",
    )
    return sum(1 for keyword in keywords if keyword in lowered)


@observe(name="hn-discussion-context")
def hn_discussion_context(ch, findings: list[dict]) -> str:
    story_ids = _hn_story_ids(findings)
    if not story_ids:
        return "No selected HN stories exposed story ids for comment summarization."

    id_list = ", ".join(str(story_id) for story_id in story_ids)
    rows = ch.query(
        f"""
        WITH
            stories AS (
                SELECT id, argMax(title, fetched_at) AS title, argMax(url, fetched_at) AS url
                FROM {config.CLICKHOUSE_DATABASE}.hn_stories
                WHERE id IN ({id_list})
                GROUP BY id
            ),
            comments AS (
                SELECT story_id, id, argMax(text, fetched_at) AS text
                FROM {config.CLICKHOUSE_DATABASE}.hn_comments
                WHERE story_id IN ({id_list})
                GROUP BY story_id, id
            ),
            pages AS (
                SELECT
                    story_id,
                    argMax(title, fetched_at) AS title,
                    argMax(text, fetched_at) AS text
                FROM {config.CLICKHOUSE_DATABASE}.hn_story_pages
                WHERE story_id IN ({id_list})
                GROUP BY story_id
            )
        SELECT
            s.id,
            any(s.title) AS title,
            any(s.url) AS url,
            any(p.title) AS page_title,
            any(p.text) AS page_text,
            groupArray(c.text) AS comments
        FROM stories AS s
        LEFT JOIN pages AS p ON p.story_id = s.id
        LEFT JOIN comments AS c ON c.story_id = s.id
        GROUP BY s.id
        HAVING length(page_text) > 0 OR length(arrayStringConcat(comments, ' ')) > 0
        ORDER BY s.id
        """,
        settings={"max_result_rows": 5, "readonly": 1},
    ).result_rows
    if not rows:
        return "No stored HN comments were available for the selected stories."

    sections = []
    for story_id, title, url, page_title, page_text, comments in rows:
        discussion_url = f"https://news.ycombinator.com/item?id={story_id}"
        source_excerpt = (page_text or "")[:3200]
        snippets = []
        sorted_comments = sorted(
            [text for text in comments if text],
            key=lambda text: (_comment_priority(text), len(text)),
            reverse=True,
        )
        for text in sorted_comments[:16]:
            if text:
                snippets.append(f"- {text[:500]}")
        sections.append(
            "\n".join(
                [
                    f"### {title}",
                    f"Story URL: {url}",
                    f"HN discussion URL: {discussion_url}",
                    f"Source page title: {page_title or title}",
                    "Source page excerpt for trigger/context:",
                    source_excerpt or "No source-page excerpt captured.",
                    "Representative comment snippets for synthesis:",
                    *snippets,
                ]
            )
        )
    return "\n\n".join(sections)


def _strip_html(raw: str) -> str:
    import re

    text = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _finding_article_urls(findings: list[dict], limit: int = 4) -> list[tuple[str, str]]:
    """(title, url) pairs for feed items in the findings, best first."""
    pairs = []
    seen = set()
    for finding in findings:
        columns = [str(col).lower() for col in finding["columns"]]
        link_idx = next((columns.index(c) for c in ("link", "url") if c in columns), None)
        title_idx = columns.index("title") if "title" in columns else None
        if link_idx is None:
            continue
        for row in finding["rows"]:
            url = str(row[link_idx] or "")
            if not url.startswith("http") or "ycombinator.com" in url or "github.com" in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            title = str(row[title_idx]) if title_idx is not None else url
            pairs.append((title, url))
    return pairs[:limit]


@observe(name="article-context")
def feed_article_context(findings: list[dict]) -> str:
    """Fetch the FULL source pages for selected feed/blog items so the briefing
    summarizes real articles, not RSS snippets."""
    sections = []
    for title, url in _finding_article_urls(findings):
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AIDevToolRadar/1.0)"},
                timeout=15,
                allow_redirects=True,
            )
            text = _strip_html(resp.text)[:3500]
            if len(text) < 200:
                continue
            sections.append(f"### {title}\nArticle URL: {url}\nFull-article excerpt:\n{text}")
        except Exception as err:
            print(f"  ! article fetch failed for {url}: {err}")
    if not sections:
        return "No full-article excerpts could be fetched for the selected feed items."
    return "\n\n".join(sections)


@observe(name="draft-briefing")
def draft_briefing(findings: list[dict], discussion: str) -> dict:
    date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    rendered = []
    for f in findings:
        lines = [f"### Goal: {f['goal']}", f"Columns: {f['columns']}"]
        lines += [str(row) for row in f["rows"][:15]]
        rendered.append("\n".join(lines))
    return llm.complete_json(
        ANALYST_SYSTEM,
        BRIEFING_PROMPT.format(
            date=date,
            hours=config.RADAR_LOOKBACK_HOURS,
            results="\n\n".join(rendered),
            discussion=discussion,
        ),
    )


@observe(name="radar-run")
def run_once(ingest_first: bool = False) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    print(f"=== Radar run {started} ===")

    ch = db.client()
    db.init(ch)

    if ingest_first:
        counts = ingest.run(ch)
    else:
        counts = {"direct_ingest": 0, "airbyte_managed": True}
        print("Skipping direct Python ingestion — analyzing data already synced into ClickHouse")

    print("Agent proposing SQL...")
    queries = propose_queries(ch)
    findings = run_queries(ch, queries)
    if not findings:
        print("No successful queries — aborting run")
        return {"published": False}

    print("Drafting cited briefing...")
    discussion = hn_discussion_context(ch, findings)
    articles = feed_article_context(findings)
    discussion = f"{discussion}\n\n## Full-article excerpts from blog/news findings\n{articles}"
    briefing = draft_briefing(findings, discussion)

    print("Grounding sources in Senso...")
    source_doc = "\n\n".join(
        f"## {f['goal']}\nSQL: `{f['sql']}`\nRows:\n"
        + "\n".join(str(r) for r in f["rows"][:15])
        for f in findings
    )
    senso.ingest_ground_truth(
        f"Radar ground truth — {started}",
        f"Ingest counts: {counts}\n\n{source_doc}\n\nHN discussion context:\n{discussion}",
    )

    print("Publishing to cited.md...")
    result = senso.publish_briefing(
        briefing["seo_title"], briefing["summary"], briefing["markdown"]
    )
    status = "PUBLISHED" if result["published"] else "saved as draft (publish rejected)"
    print(f"=== {status}: {briefing['seo_title']} ===")
    print(str(result["response"])[:800])
    return result
