"""Minimal web dashboard for AI DevTool Radar."""

import base64
import html
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import agent, airbyte, config, db, web_state

ARTICLE_URL = "https://cited.md/article/d8589037-c7f0-4aa3-957f-5c7ba0f5600b"
_run_lock = threading.Lock()


def _escape(value) -> str:
    return html.escape("" if value is None else str(value))


def _article_url(result: dict) -> str:
    response = result.get("response") or {}
    destinations = response.get("publish_destinations") or []
    if destinations:
        return destinations[0].get("display_url") or ARTICLE_URL
    return ARTICLE_URL


def _trigger_airbyte_sources() -> list[dict]:
    jobs = []
    for source in web_state.list_sources(enabled_only=True):
        connection_id = source["airbyte_connection_id"].strip()
        if not connection_id:
            jobs.append({"source": source["name"], "status": "skipped", "message": "No connection id"})
            continue
        try:
            result = airbyte.trigger_sync(connection_id)
            job = {
                "source": source["name"],
                "connection_id": connection_id,
                "trigger": result,
                "status": "triggered",
            }
            job_id = airbyte.job_id(result)
            if job_id and config.AIRBYTE_SYNC_WAIT_SECONDS:
                job["wait_result"] = airbyte.wait_for_job(job_id, config.AIRBYTE_SYNC_WAIT_SECONDS)
            jobs.append(job)
        except Exception as err:
            jobs.append({
                "source": source["name"],
                "connection_id": connection_id,
                "status": "error",
                "message": str(err),
            })
    return jobs


def run_pipeline_async(trigger: str) -> str | None:
    if not _run_lock.acquire(blocking=False):
        return None
    run_id = web_state.start_run(trigger)

    def work() -> None:
        try:
            jobs = _trigger_airbyte_sources() if airbyte.configured() else []
            result = agent.run_once(ingest_first=False)
            web_state.finish_run(
                run_id,
                "success" if result.get("published") else "completed",
                "Airbyte-managed analysis completed",
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
    return [(str(table), int(count or 0)) for table, count in rows]


def render_dashboard(message: str = "") -> str:
    sources = web_state.list_sources()
    runs = web_state.list_runs(15)
    counts = table_counts()

    source_rows = "\n".join(
        f"""
        <tr>
          <td>{_escape(source['source_type'])}</td>
          <td><strong>{_escape(source['name'])}</strong><br><span>{_escape(source['locator'])}</span></td>
          <td><code>{_escape(source['airbyte_connection_id']) or '-'}</code></td>
          <td>{'enabled' if source['enabled'] else 'paused'}</td>
          <td class="actions">
            <form method="post" action="/sources/toggle">
              <input type="hidden" name="id" value="{_escape(source['id'])}">
              <button>{'Pause' if source['enabled'] else 'Enable'}</button>
            </form>
            <form method="post" action="/sources/sync">
              <input type="hidden" name="id" value="{_escape(source['id'])}">
              <button>Sync</button>
            </form>
          </td>
        </tr>
        """
        for source in sources
    ) or '<tr><td colspan="5">No sources yet.</td></tr>'

    run_rows = "\n".join(
        f"""
        <tr>
          <td><code>{_escape(run['id'][:8])}</code></td>
          <td>{_escape(run['trigger'])}</td>
          <td><span class="pill { _escape(run['status']) }">{_escape(run['status'])}</span></td>
          <td>{_escape(run['finished_at'])}</td>
          <td>{'<a href="' + _escape(run['article_url']) + '">article</a>' if run['article_url'] else '-'}</td>
          <td>{_escape(run['message'])}</td>
        </tr>
        """
        for run in runs
    ) or '<tr><td colspan="6">No runs yet.</td></tr>'

    count_rows = "\n".join(
        f"<tr><td>{_escape(table)}</td><td>{count:,}</td></tr>"
        for table, count in counts
    )

    airbyte_status = "configured" if airbyte.configured() else "missing AIRBYTE_API_TOKEN"
    auth_status = "enabled" if config.WEB_PASSWORD else "disabled"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI DevTool Radar</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }}
    body {{ margin: 0; background: #f7f7f4; color: #1b1b18; }}
    header {{ background: #111; color: white; padding: 18px 28px; display: flex; justify-content: space-between; align-items: center; }}
    header h1 {{ margin: 0; font-size: 20px; }}
    header span {{ color: #c8c8c0; font-size: 13px; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    section {{ margin-bottom: 28px; }}
    h2 {{ font-size: 16px; margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .metric {{ background: white; border: 1px solid #deded8; border-radius: 8px; padding: 14px; }}
    .metric strong {{ display: block; font-size: 20px; }}
    .metric span {{ color: #666; font-size: 12px; }}
    form.panel, .panel {{ background: white; border: 1px solid #deded8; border-radius: 8px; padding: 16px; }}
    label {{ display: block; font-size: 12px; color: #555; margin-bottom: 5px; }}
    input, select {{ width: 100%; box-sizing: border-box; border: 1px solid #cfcfc7; border-radius: 6px; padding: 9px; font: inherit; background: white; }}
    .form-grid {{ display: grid; grid-template-columns: 160px 1fr 1.4fr 1.3fr auto; gap: 10px; align-items: end; }}
    button {{ border: 0; border-radius: 6px; background: #111; color: white; padding: 9px 12px; font: inherit; cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #deded8; border-radius: 8px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid #ecece7; padding: 10px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #f0f0eb; color: #555; font-weight: 600; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    td span {{ color: #666; }}
    .actions {{ display: flex; gap: 8px; }}
    .actions form {{ margin: 0; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 3px 8px; background: #e8e8e0; }}
    .pill.success {{ background: #d9f0df; }}
    .pill.failed {{ background: #f7d6d6; }}
    .pill.running {{ background: #fff1bf; }}
    .notice {{ background: #fff9da; border: 1px solid #eadc8a; border-radius: 8px; padding: 10px 12px; margin-bottom: 16px; }}
    @media (max-width: 900px) {{ .grid, .form-grid {{ grid-template-columns: 1fr; }} .actions {{ display: block; }} }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AI DevTool Radar</h1>
      <span>Airbyte-managed sources, scheduled intelligence runs, cited.md publishing</span>
    </div>
    <form method="post" action="/runs/start"><button>Run now</button></form>
  </header>
  <main>
    {'<div class="notice">' + _escape(message) + '</div>' if message else ''}
    <section class="grid">
      <div class="metric"><strong>{len(sources)}</strong><span>tracked sources</span></div>
      <div class="metric"><strong>{len([s for s in sources if s['enabled']])}</strong><span>enabled sources</span></div>
      <div class="metric"><strong>{_escape(airbyte_status)}</strong><span>Airbyte API</span></div>
      <div class="metric"><strong>{config.WEB_RUN_INTERVAL_HOURS:g}h</strong><span>schedule interval, auth {auth_status}</span></div>
    </section>

    <section>
      <h2>Add Source</h2>
      <form class="panel form-grid" method="post" action="/sources/add">
        <div><label>Type</label><select name="source_type"><option>github_repo</option><option>rss_feed</option><option>airbyte_connection</option></select></div>
        <div><label>Name</label><input name="name" placeholder="Stripe changelog" required></div>
        <div><label>Locator</label><input name="locator" placeholder="stripe/stripe-python or RSS URL" required></div>
        <div><label>Airbyte connection ID</label><input name="airbyte_connection_id" placeholder="optional, triggers sync"></div>
        <div><button>Add</button></div>
      </form>
    </section>

    <section>
      <h2>Sources</h2>
      <table>
        <thead><tr><th>Type</th><th>Source</th><th>Airbyte Connection</th><th>Status</th><th>Actions</th></tr></thead>
        <tbody>{source_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>Recent Runs</h2>
      <table>
        <thead><tr><th>ID</th><th>Trigger</th><th>Status</th><th>Finished</th><th>Output</th><th>Message</th></tr></thead>
        <tbody>{run_rows}</tbody>
      </table>
    </section>

    <section>
      <h2>ClickHouse Tables</h2>
      <table>
        <thead><tr><th>Table</th><th>Rows</th></tr></thead>
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
            if self.path == "/sources/add":
                source_id = web_state.add_source(
                    form.get("source_type", "github_repo"),
                    form.get("name", "").strip(),
                    form.get("locator", "").strip(),
                    form.get("airbyte_connection_id", "").strip(),
                )
                run_id = run_pipeline_async(f"source-added:{source_id}")
                self._redirect("Source added; run queued" if run_id else "Source added; run already active")
            elif self.path == "/sources/toggle":
                source = web_state.get_source(form.get("id", ""))
                if source:
                    web_state.set_source_enabled(source["id"], not source["enabled"])
                self._redirect("Source updated")
            elif self.path == "/sources/sync":
                source = web_state.get_source(form.get("id", ""))
                if source and source["airbyte_connection_id"]:
                    airbyte.trigger_sync(source["airbyte_connection_id"])
                    self._redirect("Airbyte sync triggered")
                else:
                    self._redirect("Source has no Airbyte connection id")
            elif self.path == "/runs/start":
                run_id = run_pipeline_async("manual")
                self._redirect("Run queued" if run_id else "Run already active")
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
    print(f"Scheduled Airbyte-managed runs every {config.WEB_RUN_INTERVAL_HOURS:g} hours")
    server.serve_forever()


if __name__ == "__main__":
    main()
