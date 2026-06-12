"""Senso API client: ground-truth ingestion + publishing to cited.md.

API surface (base: https://apiv2.senso.ai/api/v1, auth: X-API-Key):
  POST /org/kb/raw                  {title, text}                      -> knowledge base item
  POST /org/content-engine/draft    {raw_markdown, seo_title, summary} -> draft
  POST /org/content-engine/publish  same body (+publisher_ids?)        -> live on destinations
  GET  /org/destinations            list destinations (citeables = cited.md by default)
  GET  /org/me                      auth check
"""

import requests

from . import config


class SensoError(RuntimeError):
    pass


def _request(method: str, path: str, body: dict | None = None):
    resp = requests.request(
        method,
        f"{config.SENSO_BASE_URL}{path}",
        headers={
            "X-API-Key": config.SENSO_API_KEY,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body else {}),
        },
        json=body,
        timeout=60,
    )
    if not resp.ok:
        raise SensoError(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def whoami():
    return _request("GET", "/org/me")


def destinations():
    return _request("GET", "/org/destinations")


def ingest_ground_truth(title: str, markdown_text: str):
    """Store the agent's source material as a verified knowledge-base item."""
    return _request("POST", "/org/kb/raw", {"title": title, "text": markdown_text})


_question_id: str | None = None


def ensure_question_id() -> str:
    """Drafts require a geo question; reuse the configured one or create ours."""
    global _question_id
    if config.SENSO_QUESTION_ID:
        return config.SENSO_QUESTION_ID
    if _question_id:
        return _question_id
    created = _request(
        "POST",
        "/org/prompts",
        {
            "question_text": "What is happening in the AI developer tools ecosystem right now?",
            "type": "awareness",
        },
    )
    _question_id = (
        created.get("geo_question_id") or created.get("id") or created.get("prompt_id")
        or (created.get("prompt") or {}).get("id")
    )
    print(f"  created Senso prompt {_question_id} (set SENSO_QUESTION_ID to reuse)")
    return _question_id


def publish_briefing(seo_title: str, summary: str, raw_markdown: str):
    """Publish to all configured destinations (cited.md/citeables by default).

    Falls back to saving a draft if direct publish is rejected, so a run
    never loses its output.
    """
    body = {
        "raw_markdown": raw_markdown,
        "seo_title": seo_title,
        "summary": summary,
        "geo_question_id": ensure_question_id(),
    }
    if config.SENSO_PUBLISHER_ID:
        body["publisher_ids"] = [config.SENSO_PUBLISHER_ID]
    try:
        return {"published": True, "response": _request("POST", "/org/content-engine/publish", body)}
    except SensoError as err:
        print(f"  publish failed ({err}); saving as draft instead")
        return {"published": False, "response": _request("POST", "/org/content-engine/draft", body)}
