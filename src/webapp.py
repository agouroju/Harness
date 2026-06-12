"""Web dashboard for AI DevTool Radar.

Users manage WHAT the radar watches (GitHub repos + blog/news feeds); the app
manages HOW: every tracked source becomes a real Airbyte pipeline into
ClickHouse, and scheduled runs analyze the data and publish a cited briefing.
"""

import base64
import html
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import agent, airbyte, config, db, pipelines, watchlist, web_state

ARTICLE_URL = "https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b"
_run_lock = threading.Lock()

INTERNAL_TABLES = {"watch_sources", "radar_runs"}


def _escape(value) -> str:
    return html.escape("" if value is None else str(value))


def _article_url(result: dict) -> str:
    response = result.get("response") or {}
    destinations = response.get("publish_destinations") or []
    if destinations:
        return destinations[0].get("display_url") or ARTICLE_URL
    return ARTICLE_URL


def _trigger_all_syncs() -> list[dict]:
    """Kick every Airbyte pipeline so the analysis sees fresh data."""
    jobs = []
    try:
        connections = airbyte.list_connections()
    except Exception as err:
        return [{"status": "error", "message": str(err)}]
    for conn in connections:
        try:
            airbyte.trigger_sync(conn["connectionId"])
            jobs.append({"source": conn.get("name", ""), "status": "triggered"})
        except Exception as err:
            jobs.append({"source": conn.get("name", ""), "status": "error", "message": str(err)})
    if jobs and config.AIRBYTE_SYNC_WAIT_SECONDS:
        time.sleep(min(config.AIRBYTE_SYNC_WAIT_SECONDS, 300))
    return jobs


def run_pipeline_async(trigger: str) -> str | None:
    if not _run_lock.acquire(blocking=False):
        return None
    run_id = web_state.start_run(trigger)

    def work() -> None:
        try:
            jobs = _trigger_all_syncs() if airbyte.configured() else []
            result = agent.run_once(ingest_first=False)
            web_state.finish_run(
                run_id,
                "success" if result.get("published") else "completed",
                "Synced sources and published briefing",
                _article_url(result),
                jobs,
            )
        except Exception as err:
            web_state.finish_run(run_id, "failed", str(err), jobs=[])
        finally:
            _run_lock.release()

    threading.Thread(target=work, daemon=True).start()
    return run_id


def scheduler_loop() -> None:
    interval = max(config.WEB_RUN_INTERVAL_HOURS * 3600, 60)
    while True:
        time.sleep(interval)
        run_pipeline_async("schedule")


def table_counts() -> list[tuple[str, int]]:
    ch = db.client()
    rows = ch.query(
        f"""
        SELECT table, sum(total_rows)
        FROM system.tables
        WHERE database IN ('{config.CLICKHOUSE_DATABASE}', 'radar_airbyte')
        GROUP BY table
        ORDER BY table
        """,
    ).result_rows
    return [
        (str(table), int(count or 0))
        for table, count in rows
        if str(table) not in INTERNAL_TABLES
    ]


def _friendly_table(name: str) -> str:
    if name.endswith("__items"):
        return f"Feed: {name.removesuffix('__items').replace('_', ' ')}"
    pretty = {
        "issues": "GitHub issues & PRs (Airbyte)",
        "repositories": "GitHub repositories (Airbyte)",
        "github_issues": "GitHub issues & PRs (direct)",
        "github_repo_stats": "GitHub star snapshots",
        "hn_stories": "Hacker News stories",
        "hn_comments": "Hacker News comments",
        "hn_story_pages": "Story page excerpts",
    }
    return pretty.get(name, name)


def render_dashboard(message: str = "") -> str:
    repos = config._load_tracked_repos()
    feeds = config._load_tracked_feeds()
    runs = web_state.list_runs(15)
    counts = table_counts()

    repo_rows = "\n".join(
        f"""
        <tr>
          <td><strong>{_escape(repo)}</strong><br><span>github.com/{_escape(repo)}</span></td>
          <td class="actions">
            <form method="post" action="/watch/remove">
              <input type="hidden" name="kind" value="repo">
              <input type="hidden" name="value" value="{_escape(repo)}">
              <button class="ghost">Stop tracking</button>
            </form>
          </td>
        </tr>
        """
        for repo in repos
    ) or '<tr><td colspan="2">No repositories tracked yet.</td></tr>'

    feed_rows = "\n".join(
        f"""
        <tr>
          <td><strong>{_escape(pipelines.feed_slug(feed).replace('_', ' '))}</strong><br><span>{_escape(feed)}</span></td>
          <td class="actions">
            <form method="post" action="/watch/remove">
              <input type="hidden" name="kind" value="feed">
              <input type="hidden" name="value" value="{_escape(feed)}">
              <button class="ghost">Stop tracking</button>
            </form>
          </td>
        </tr>
        """
        for feed in feeds
    ) or '<tr><td colspan="2">No feeds tracked yet.</td></tr>'

    run_rows = "\n".join(
        f"""
        <tr>
          <td>{_escape(run['finished_at'] or 'in progress')}</td>
          <td>{_escape({'manual': 'Run button', 'schedule': 'Automatic'}.get(run['trigger'], run['trigger']))}</td>
          <td><span class="pill { _escape(run['status']) }">{_escape(run['status'])}</span></td>
          <td>{'<a href="' + _escape(run['article_url']) + '" target="_blank">Read the briefing →</a>' if run['article_url'] else '—'}</td>
          <td>{_escape(run['message'])}</td>
        </tr>
        """
        for run in runs
    ) or '<tr><td colspan="5">No briefings yet — press "Sync & publish briefing".</td></tr>'

    count_rows = "\n".join(
        f"<tr><td>{_escape(_friendly_table(table))}</td><td>{count:,}</td></tr>"
        for table, count in counts
    )

    airbyte_ok = airbyte.configured()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI DevTool Radar</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }}
    body {{ margin: 0; background: #f7f7f4; color: #1b1b18; }}
    header {{ background: #111; color: white; padding: 18px 28px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }}
    header h1 {{ margin: 0; font-size: 20px; }}
    header span {{ color: #c8c8c0; font-size: 13px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    section {{ margin-bottom: 28px; }}
    h2 {{ font-size: 16px; margin: 0 0 6px; }}
    .hint {{ color: #666; font-size: 13px; margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .metric {{ background: white; border: 1px solid #deded8; border-radius: 8px; padding: 14px; }}
    .metric strong {{ display: block; font-size: 20px; }}
    .metric span {{ color: #666; font-size: 12px; }}
    form.panel, .panel {{ background: white; border: 1px solid #deded8; border-radius: 8px; padding: 16px; }}
    label {{ display: block; font-size: 12px; color: #555; margin-bottom: 5px; }}
    input, select {{ width: 100%; box-sizing: border-box; border: 1px solid #cfcfc7; border-radius: 6px; padding: 9px; font: inherit; background: white; }}
    .form-grid {{ display: grid; grid-template-columns: 220px 1fr auto; gap: 10px; align-items: end; }}
    button {{ border: 0; border-radius: 6px; background: #111; color: white; padding: 9px 14px; font: inherit; cursor: pointer; }}
    button.ghost {{ background: transparent; color: #a33; border: 1px solid #d8c2c2; padding: 6px 10px; font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #deded8; border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #ecece7; padding: 10px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #f0f0eb; color: #555; font-weight: 600; }}
    td span {{ color: #666; font-size: 12px; }}
    .actions {{ width: 1%; white-space: nowrap; }}
    .actions form {{ margin: 0; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 3px 8px; background: #e8e8e0; }}
    .pill.success {{ background: #d9f0df; }}
    .pill.failed {{ background: #f7d6d6; }}
    .pill.running {{ background: #fff1bf; }}
    .notice {{ background: #fff9da; border: 1px solid #eadc8a; border-radius: 8px; padding: 10px 12px; margin-bottom: 16px; }}
    a {{ color: #0a58ca; }}
    @media (max-width: 900px) {{ .grid, .form-grid, .cols {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AI DevTool Radar</h1>
      <span>Watches the AI ecosystem for you and publishes a cited daily briefing — automatically.</span>
    </div>
    <form method="post" action="/runs/start"><button>Sync &amp; publish briefing</button></form>
  </header>
  <main>
    {'<div class="notice">' + _escape(message) + '</div>' if message else ''}
    <section class="grid">
      <div class="metric"><strong>{len(repos)}</strong><span>GitHub repos tracked</span></div>
      <div class="metric"><strong>{len(feeds)}</strong><span>blogs &amp; news feeds tracked</span></div>
      <div class="metric"><strong>{'connected' if airbyte_ok else 'not connected'}</strong><span>Airbyte data pipelines</span></div>
      <div class="metric"><strong>every {config.WEB_RUN_INTERVAL_HOURS:g}h</strong><span>automatic briefing schedule</span></div>
    </section>

    <section>
      <h2>Track a new source</h2>
      <p class="hint">Add a GitHub repository or any blog/news RSS feed. The radar creates the data pipeline for you — no setup needed.</p>
      <form class="panel form-grid" method="post" action="/watch/add">
        <div><label>Source type</label>
          <select name="kind">
            <option value="repo">GitHub repository</option>
            <option value="feed">Blog or news feed (RSS)</option>
          </select>
        </div>
        <div><label>Repository (owner/name) or feed URL</label><input name="value" placeholder="e.g. vercel/ai &nbsp;or&nbsp; https://blog.example.com/rss" required></div>
        <div><button>Start tracking</button></div>
      </form>
    </section>

    <section class="cols">
      <div>
        <h2>Tracked GitHub repositories</h2>
        <p class="hint">Issues, pull requests, and stars are synced hourly.</p>
        <table>
          <thead><tr><th>Repository</th><th></th></tr></thead>
          <tbody>{repo_rows}</tbody>
        </table>
      </div>
      <div>
        <h2>Tracked blogs &amp; news feeds</h2>
        <p class="hint">New posts are synced hourly via Airbyte.</p>
        <table>
          <thead><tr><th>Feed</th><th></th></tr></thead>
          <tbody>{feed_rows}</tbody>
        </table>
      </div>
    </section>

    <section>
      <h2>Published briefings</h2>
      <p class="hint">Each run analyzes the freshest data and publishes a fully-cited article to cited.md.</p>
      <table>
        <thead><tr><th>Finished</th><th>Started by</th><th>Status</th><th>Briefing</th><th>Notes</th></tr></thead>
        <tbody>{run_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Live data</h2>
      <p class="hint">What the radar currently knows — rows synced into ClickHouse.</p>
      <table>
        <thead><tr><th>Dataset</th><th>Rows</th></tr></thead>
        <tbody>{count_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _authorized(self) -> bool:
        if not config.WEB_PASSWORD:
            return True
        header = self.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header.removeprefix("Basic ")).decode()
        except Exception:
            return False
        username, _, password = raw.partition(":")
        expected_user = config.WEB_USERNAME or "admin"
        return username == expected_user and password == config.WEB_PASSWORD

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="AI DevTool Radar"')
        self.end_headers()
        return False

    def _send_html(self, body: str, status: int = 200) -> None:
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, message: str = "") -> None:
        target = "/"
        if message:
            target += "?message=" + message.replace(" ", "+")
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", target)
        self.end_headers()

    def _form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode()
        parsed = parse_qs(body)
        return {key: values[0] for key, values in parsed.items()}

    def _apply_watch_change(self) -> str:
        """Reconcile Airbyte after a watchlist edit; report what happened."""
        if not airbyte.configured():
            return "Saved. (Airbyte API not connected — pipeline not created yet.)"
        report = pipelines.reconcile()
        parts = []
        if report["created"]:
            parts.append("pipeline created and first sync started")
        if report["deleted"]:
            parts.append("pipeline removed")
        if report["github_repos"]:
            parts.append(f"GitHub sync now covers {report['github_repos']} repos")
        return "Saved — " + (", ".join(parts) if parts else "pipelines already up to date")

    def do_GET(self) -> None:
        if not self._require_auth():
            return
        parsed = urlparse(self.path)
        if parsed.path != "/":
            self._send_html("Not found", 404)
            return
        message = parse_qs(parsed.query).get("message", [""])[0]
        self._send_html(render_dashboard(message))

    def do_POST(self) -> None:
        if not self._require_auth():
            return
        form = self._form()
        try:
            if self.path == "/watch/add":
                kind = form.get("kind", "repo")
                value = form.get("value", "").strip()
                if kind == "feed":
                    feed, changed = watchlist.add_feed(value)
                    label = feed
                else:
                    repo, changed = watchlist.add_repo(value)
                    label = repo
                if not changed:
                    self._redirect(f"Already tracking {label}")
                    return
                self._redirect(f"Now tracking {label}. {self._apply_watch_change()}")
            elif self.path == "/watch/remove":
                kind = form.get("kind", "repo")
                value = form.get("value", "").strip()
                if kind == "feed":
                    watchlist.remove_feed(value)
                else:
                    watchlist.remove_repo(value)
                self._redirect(f"Stopped tracking. {self._apply_watch_change()}")
            elif self.path == "/runs/start":
                run_id = run_pipeline_async("manual")
                self._redirect(
                    "Briefing run started — syncing sources, this takes a few minutes"
                    if run_id else "A run is already in progress"
                )
            else:
                self._send_html("Not found", 404)
        except Exception as err:
            self._redirect(f"Error: {err}")

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    web_state.init()
    if config.WEB_SCHEDULER_ENABLED:
        threading.Thread(target=scheduler_loop, daemon=True).start()
    server = ThreadingHTTPServer((config.WEB_HOST, config.WEB_PORT), Handler)
    print(f"AI DevTool Radar web app listening on http://{config.WEB_HOST}:{config.WEB_PORT}")
    print(f"Automatic briefing runs every {config.WEB_RUN_INTERVAL_HOURS:g} hours")
    server.serve_forever()


if __name__ == "__main__":
    main()
