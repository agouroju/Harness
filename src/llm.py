"""OpenAI-compatible LLM client, traced by Langfuse when keys are configured."""

import json

from . import config

if config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY:
    from langfuse.openai import OpenAI  # drop-in client with automatic tracing
else:
    from openai import OpenAI

_kwargs = {"api_key": config.OPENAI_API_KEY}
if config.OPENAI_BASE_URL:
    _kwargs["base_url"] = config.OPENAI_BASE_URL
_client = OpenAI(**_kwargs)


def complete(system: str, user: str, json_mode: bool = False) -> str:
    resp = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
        **({"response_format": {"type": "json_object"}} if json_mode else {}),
    )
    return resp.choices[0].message.content


def complete_json(system: str, user: str) -> dict:
    text = complete(system, user, json_mode=True)
    return json.loads(text)
