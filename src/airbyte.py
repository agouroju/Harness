"""Small Airbyte API client used by the web app."""

import time
from typing import Any

import requests

from . import config


class AirbyteError(RuntimeError):
    pass


_token_cache: dict[str, Any] = {"token": "", "expires": 0.0}


def configured() -> bool:
    return bool(config.AIRBYTE_API_TOKEN or (config.AIRBYTE_CLIENT_ID and config.AIRBYTE_CLIENT_SECRET))


def _access_token() -> str:
    """Static token if provided, else mint (and cache) one from client credentials."""
    if config.AIRBYTE_API_TOKEN:
        return config.AIRBYTE_API_TOKEN
    if not (config.AIRBYTE_CLIENT_ID and config.AIRBYTE_CLIENT_SECRET):
        raise AirbyteError("Set AIRBYTE_API_TOKEN or AIRBYTE_CLIENT_ID/AIRBYTE_CLIENT_SECRET")
    if _token_cache["token"] and time.time() < _token_cache["expires"]:
        return _token_cache["token"]
    resp = requests.post(
        f"{config.AIRBYTE_API_URL}/applications/token",
        json={
            "client_id": config.AIRBYTE_CLIENT_ID,
            "client_secret": config.AIRBYTE_CLIENT_SECRET,
            "grant-type": "client_credentials",
        },
        timeout=30,
    )
    if not resp.ok:
        raise AirbyteError(f"token grant failed: HTTP {resp.status_code}: {resp.text[:300]}")
    token = resp.json().get("access_token", "")
    _token_cache["token"] = token
    _token_cache["expires"] = time.time() + 120  # tokens are short-lived; refresh often
    return token


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{config.AIRBYTE_API_URL}{path}"
    resp = requests.request(method, url, headers=_headers(), json=body, timeout=60)
    if not resp.ok:
        raise AirbyteError(f"{method} {path} -> HTTP {resp.status_code}: {resp.text[:500]}")
    if not resp.text:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def list_sources() -> list[dict[str, Any]]:
    data = _request("GET", f"/sources?workspaceIds={config.AIRBYTE_WORKSPACE_ID}&limit=100")
    return data.get("data", [])


def list_connections() -> list[dict[str, Any]]:
    data = _request("GET", f"/connections?workspaceIds={config.AIRBYTE_WORKSPACE_ID}&limit=100")
    return data.get("data", [])


def create_rss_source(name: str, feed_url: str) -> dict[str, Any]:
    return _request("POST", "/sources", {
        "name": name,
        "workspaceId": config.AIRBYTE_WORKSPACE_ID,
        "configuration": {"sourceType": "rss", "url": feed_url},
    })


def delete_source(source_id: str) -> None:
    _request("DELETE", f"/sources/{source_id}")


def delete_connection(connection_id: str) -> None:
    _request("DELETE", f"/connections/{connection_id}")


def create_connection(source_id: str, name: str, prefix: str) -> dict[str, Any]:
    return _request("POST", "/connections", {
        "name": name,
        "sourceId": source_id,
        "destinationId": config.AIRBYTE_DESTINATION_ID,
        "namespaceDefinition": "destination",
        "prefix": prefix,
        "schedule": {"scheduleType": "cron", "cronExpression": "0 0 * * * ?"},
    })


def update_github_repositories(repos: list[str]) -> dict[str, Any]:
    """Replace the GitHub source's repository list (requires GITHUB_TOKEN for credentials)."""
    if not config.AIRBYTE_GITHUB_SOURCE_ID:
        raise AirbyteError("AIRBYTE_GITHUB_SOURCE_ID is not configured")
    if not config.GITHUB_TOKEN:
        raise AirbyteError("GITHUB_TOKEN is required to update the GitHub source credentials")
    return _request("PATCH", f"/sources/{config.AIRBYTE_GITHUB_SOURCE_ID}", {
        "configuration": {
            "sourceType": "github",
            "credentials": {
                "option_title": "PAT Credentials",
                "personal_access_token": config.GITHUB_TOKEN,
            },
            "repositories": repos,
        },
    })


def trigger_sync(connection_id: str) -> dict[str, Any]:
    """Trigger a sync for a connection.

    Airbyte Cloud's public API and the legacy config API have used different
    endpoint shapes. Try the modern job endpoint first, then compatible fallbacks.
    """
    connection_id = connection_id.strip()
    if not connection_id:
        raise AirbyteError("Missing Airbyte connection id")

    attempts = [
        ("POST", "/jobs", {"connectionId": connection_id, "jobType": "sync"}),
        ("POST", f"/connections/{connection_id}/sync", None),
        ("POST", "/connections/sync", {"connectionId": connection_id}),
    ]
    last_error = None
    for method, path, body in attempts:
        try:
            result = _request(method, path, body)
            result.setdefault("connectionId", connection_id)
            return result
        except AirbyteError as err:
            last_error = err
            if "HTTP 404" not in str(err) and "HTTP 405" not in str(err):
                raise
    raise last_error or AirbyteError("Unable to trigger sync")


def job_id(result: dict[str, Any]) -> str:
    for key in ("jobId", "id"):
        value = result.get(key)
        if value:
            return str(value)
    nested = result.get("job") or {}
    for key in ("id", "jobId"):
        value = nested.get(key)
        if value:
            return str(value)
    return ""


def get_job(job_id_value: str) -> dict[str, Any]:
    if not job_id_value:
        return {}
    attempts = [
        ("GET", f"/jobs/{job_id_value}", None),
        ("POST", "/jobs/get", {"id": int(job_id_value) if job_id_value.isdigit() else job_id_value}),
    ]
    last_error = None
    for method, path, body in attempts:
        try:
            return _request(method, path, body)
        except AirbyteError as err:
            last_error = err
            if "HTTP 404" not in str(err) and "HTTP 405" not in str(err):
                raise
    raise last_error or AirbyteError("Unable to read job")


def wait_for_job(job_id_value: str, timeout_seconds: int) -> dict[str, Any]:
    if not job_id_value or timeout_seconds <= 0:
        return {}
    deadline = time.time() + timeout_seconds
    latest = {}
    while time.time() < deadline:
        latest = get_job(job_id_value)
        status = str(latest.get("status") or (latest.get("job") or {}).get("status") or "").lower()
        if status in {"succeeded", "failed", "cancelled", "incomplete"}:
            return latest
        time.sleep(5)
    return latest
